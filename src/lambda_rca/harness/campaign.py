"""Injection campaign: one fault at a time, steady state -> fault -> recovery (Section 4.2).

For every planned window the campaign
  1. optionally makes a benign commit in the app repository,
  2. injects the fault (none for normal windows) and records the start time,
  3. runs CloudFormation drift detection at a fixed offset inside the window,
  4. waits until the end of the window and takes a configuration snapshot,
  5. in "hold" mode runs the agent for every ablation level while the fault is active,
  6. reverts the fault, writes the label and waits for the recovery period.
The revert runs in a `finally` block, and the saved original state is persisted before
injection, so a crash can be repaired with `lambda-rca recover` (requirement R2).
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from ..aws import resolve_functions, session
from ..config import Config
from ..io import append_jsonl, iso, read_json, read_jsonl, utcnow, write_json
from ..labels import ACCEPTED_LAYERS, Label
from . import apprepo
from .faults import FAULTS, FaultContext
from .snapshot import detect_drift, take_snapshot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedWindow:
    window_id: str
    fault_type: str        # F1..F6 or N
    function: str | None
    repetition: int


def plan_windows(cfg: Config) -> list[PlannedWindow]:
    """Planned dataset (Section 4.4): 5 fault types x 4 functions x 3 repetitions,
    plus silent-drift and normal windows, in a seeded random order. Window ids are
    neutral (W001, ...) so that they reveal nothing about the fault to the agent."""
    c = cfg["campaign"]
    functions = list(cfg.functions)
    items: list[tuple[str, str | None, int]] = []
    for fault in c["symptomatic_faults"]:
        for fn in functions:
            for rep in range(1, c["repetitions"] + 1):
                items.append((fault, fn, rep))
    for i in range(c["silent_windows"]):
        items.append(("F6", functions[i % len(functions)], i // len(functions) + 1))
    for i in range(c["normal_windows"]):
        items.append(("N", None, i + 1))
    random.Random(c["seed"]).shuffle(items)
    return [PlannedWindow(f"W{i + 1:03d}", f, fn, rep) for i, (f, fn, rep) in enumerate(items)]


class Campaign:
    def __init__(self, cfg: Config, analyse: Callable[[dict], None] | None = None, dry_run: bool = False):
        self.cfg = cfg
        self.analyse = analyse
        self.dry_run = dry_run
        self.state_file = cfg.path("data_dir") / "harness_state.json"
        if not dry_run:
            s = session(cfg, "harness")
            self.lam, self.iam, self.cfn = s.client("lambda"), s.client("iam"), s.client("cloudformation")
            self.functions = resolve_functions(cfg, "harness")

    # ------------------------------------------------------------------ public
    def run(self, only: list[str] | None = None, limit: int | None = None) -> None:
        done = {r["incident_id"] for r in read_jsonl(self.cfg.path("labels_file"))}
        plan = [w for w in plan_windows(self.cfg) if w.window_id not in done]
        if only:
            plan = [w for w in plan if w.window_id in only]
        if not self.dry_run and any(w.fault_type == "F4" for w in plan) and not self._f4_possible():
            log.warning("account concurrency limit too low for reserved concurrency (F4); "
                        "F4 windows are postponed until the quota increase is approved")
            plan = [w for w in plan if w.fault_type != "F4"]
        if limit:
            plan = plan[:limit]
        log.info("%d windows to run (%d already labelled)", len(plan), len(done))
        every = self.cfg["campaign"].get("noise_commits_every") or 0
        for n, w in enumerate(plan):
            if every and n % every == 0 and self.cfg.app_repo.exists() and not self.dry_run:
                apprepo.benign_commit(self.cfg.app_repo, n)
            self.run_window(w)

    def _f4_possible(self) -> bool:
        """Reserved concurrency must leave at least 10 unreserved executions in the account."""
        limit = self.lam.get_account_settings()["AccountLimit"]["ConcurrentExecutions"]
        return limit - self.cfg["faults"]["F4"]["reserved_concurrency"] >= 10 + 1

    def run_window(self, w: PlannedWindow) -> Label:
        c = self.cfg["campaign"]
        log.info("window %s: %s on %s (rep %d)", w.window_id, w.fault_type, w.function, w.repetition)
        if self.dry_run:
            return self._dry_label(w)

        fault, injection = None, None
        snapshots_dir = self.cfg.path("snapshots_dir")
        try:
            if w.fault_type != "N":
                fn = self.functions[w.function]
                fault = FAULTS[w.fault_type](FaultContext(self.cfg, self.lam, self.iam, fn,
                                                          self.cfg.functions[w.function]))
                injection = fault.inject()
                write_json(self.state_file, {"window": w.__dict__, "saved": injection.saved})
            start = utcnow()
            end = start + timedelta(minutes=c["fault_minutes"])

            self._sleep_until(start + timedelta(minutes=c["drift_check_offset_minutes"]))
            drift = self._safe(lambda: detect_drift(self.cfn, self.cfg.stack_name), "drift detection")
            write_json(self.cfg.path("baselines_dir") / "cfn_drift" / f"{w.window_id}.json",
                       {"window_id": w.window_id, **(drift or {"error": "failed"})})

            self._sleep_until(end)
            snap = self._safe(lambda: take_snapshot(self.cfg, self.lam, self.iam, self.functions), "snapshot")
            write_json(snapshots_dir / f"{w.window_id}.json", snap)

            label = self._label(w, start, end, injection, fault)
            window = label.window_record()
            append_jsonl(self.cfg.path("windows_file"), window)

            if c["analysis_mode"] == "hold" and self.analyse:
                self.analyse(window)
        finally:
            if fault and injection:
                fault.revert(injection.saved)
                self.state_file.unlink(missing_ok=True)
                log.info("window %s: reverted", w.window_id)

        append_jsonl(self.cfg.path("labels_file"), label.to_dict())
        time.sleep(c["recovery_minutes"] * 60)
        return label

    def recover(self) -> bool:
        """Revert a fault left active by an interrupted campaign."""
        if not self.state_file.exists():
            return False
        state = read_json(self.state_file)
        w = state["window"]
        fault = FAULTS[w["fault_type"]](FaultContext(self.cfg, self.lam, self.iam, self.functions[w["function"]],
                                                     self.cfg.functions[w["function"]]))
        fault.revert(state["saved"])
        self.state_file.unlink()
        return True

    def steady_state(self, minutes: int | None = None) -> dict:
        """Record a fault-free period used only to train Isolation Forest (Section 5.5)."""
        minutes = minutes or self.cfg["campaign"]["steady_state_minutes"]
        start = utcnow()
        log.info("recording %d minutes of steady state", minutes)
        time.sleep(minutes * 60)
        rec = {"start": iso(start), "end": iso(utcnow())}
        write_json(self.cfg.path("data_dir") / "labels" / "steady_state.json", rec)
        return rec

    # ------------------------------------------------------------------ internals
    def _label(self, w: PlannedWindow, start, end, injection, fault) -> Label:
        if injection is None:
            return Label(incident_id=w.window_id, start_time=iso(start), end_time=iso(end), fault_type="N",
                         subtype="none", function=None, root_cause_layer="NONE", root_cause_artifact=None,
                         symptomatic=False, accepted_layers=ACCEPTED_LAYERS["N"], artifact_match=[],
                         details={"repetition": w.repetition})
        return Label(
            incident_id=w.window_id, start_time=iso(start), end_time=iso(end), fault_type=w.fault_type,
            subtype=injection.subtype, function=w.function, root_cause_layer=injection.root_cause_layer,
            root_cause_artifact=injection.root_cause_artifact, symptomatic=fault.symptomatic,
            accepted_layers=fault.accepted_layers, artifact_match=injection.artifact_match,
            details={"repetition": w.repetition, **injection.details})

    def _dry_label(self, w: PlannedWindow) -> Label:
        now = utcnow()
        return Label(w.window_id, iso(now), iso(now), w.fault_type, "dry-run", w.function, "NONE", None)

    @staticmethod
    def _sleep_until(t) -> None:
        delay = (t - utcnow()).total_seconds()
        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _safe(fn, what):
        try:
            return fn()
        except Exception:  # a failed measurement must not prevent the revert
            log.exception("%s failed", what)
            return None
