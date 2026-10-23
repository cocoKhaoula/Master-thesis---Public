"""Fault catalogue F1-F6 (thesis Table 4.1 and Appendix A).

Every fault stores the original configuration *before* it changes anything, so that the
revert is exact (requirement R2). The saved state is also persisted by the campaign, so
that `lambda-rca recover` can restore it after a crash.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..aws import FunctionResources
from ..config import Config
from ..labels import ACCEPTED_LAYERS
from . import apprepo
from .policy import add_unused_permission, edit_template_env_var, remove_action, set_env_var


@dataclass
class FaultContext:
    cfg: Config
    lam: Any                  # boto3 lambda client (harness role)
    iam: Any                  # boto3 iam client (harness role)
    fn: FunctionResources
    fn_cfg: dict[str, Any]    # entry of config `functions`


@dataclass
class Injection:
    """Result of an injection: the label fields and the state needed to revert."""
    subtype: str
    root_cause_layer: str
    root_cause_artifact: str | None
    artifact_match: list[list[str]]
    saved: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


class Fault(ABC):
    fault_type: str
    symptomatic: bool = True

    def __init__(self, ctx: FaultContext):
        self.ctx = ctx

    @abstractmethod
    def inject(self) -> Injection: ...

    @abstractmethod
    def revert(self, saved: dict[str, Any]) -> None: ...

    @property
    def accepted_layers(self) -> list[str]:
        return ACCEPTED_LAYERS[self.fault_type]

    # -------------------------------------------------------------- helpers
    def _wait_updated(self) -> None:
        """Wait until the function update has completed (Appendix A, implementation notes)."""
        self.ctx.lam.get_waiter("function_updated_v2").wait(FunctionName=self.ctx.fn.function_name)

    def _policy_name(self) -> str:
        return self.ctx.cfg["inline_policy_name"]

    def _get_policy(self) -> dict[str, Any]:
        resp = self.ctx.iam.get_role_policy(RoleName=self.ctx.fn.role_name, PolicyName=self._policy_name())
        return resp["PolicyDocument"]   # boto3 returns the decoded document

    def _put_policy(self, doc: dict[str, Any]) -> None:
        import json
        self.ctx.iam.put_role_policy(RoleName=self.ctx.fn.role_name, PolicyName=self._policy_name(),
                                     PolicyDocument=json.dumps(doc))

    @staticmethod
    def _iam_settle(seconds: int = 15) -> None:
        # IAM is eventually consistent (Amazon Web Services, 2026f); give the change time
        # to propagate before the window starts.
        time.sleep(seconds)


class RemovePermission(Fault):
    """F1 - remove the function's primary write action from its execution role."""
    fault_type = "F1"

    def inject(self) -> Injection:
        action = self.ctx.fn_cfg["primary_action"]
        original = self._get_policy()
        reduced = remove_action(original, action)
        if reduced["Statement"]:
            self._put_policy(reduced)
        else:
            # the action was the only permission: IAM rejects a policy without statements,
            # so the inline policy is removed (the revert puts the original back)
            self.ctx.iam.delete_role_policy(RoleName=self.ctx.fn.role_name, PolicyName=self._policy_name())
        self._iam_settle()
        return Injection(
            subtype="drift", root_cause_layer="IAM",
            root_cause_artifact=f"{self.ctx.fn.role_name}/{self._policy_name()}: {action} removed",
            artifact_match=[[action.split(":")[1]]],
            saved={"policy": original}, details={"action": action})

    def revert(self, saved):
        self._put_policy(saved["policy"])
        self._iam_settle()


class LowerMemoryTimeout(Fault):
    """F2 - lower memory and timeout out-of-band."""
    fault_type = "F2"

    def inject(self) -> Injection:
        p = self.ctx.cfg["faults"]["F2"]
        conf = self.ctx.lam.get_function_configuration(FunctionName=self.ctx.fn.function_name)
        saved = {"MemorySize": conf["MemorySize"], "Timeout": conf["Timeout"]}
        self.ctx.lam.update_function_configuration(FunctionName=self.ctx.fn.function_name,
                                                   MemorySize=p["memory_size"], Timeout=p["timeout"])
        self._wait_updated()
        return Injection(
            subtype="drift", root_cause_layer="CONFIG",
            root_cause_artifact=f"{self.ctx.fn.function_name}: MemorySize {saved['MemorySize']}->"
                                f"{p['memory_size']}, Timeout {saved['Timeout']}->{p['timeout']}",
            artifact_match=[["memory"], ["timeout"]],
            saved=saved, details={"new": {"MemorySize": p["memory_size"], "Timeout": p["timeout"]}})

    def revert(self, saved):
        self.ctx.lam.update_function_configuration(FunctionName=self.ctx.fn.function_name, **saved)
        self._wait_updated()


class WrongEnvVar(Fault):
    """F3 - wrong environment variable (out-of-band drift)."""
    fault_type = "F3"

    def inject(self) -> Injection:
        var, bad = self.ctx.fn_cfg["env_var"], self.ctx.fn_cfg["env_bad_value"]
        conf = self.ctx.lam.get_function_configuration(FunctionName=self.ctx.fn.function_name)
        original = conf.get("Environment", {}).get("Variables", {})
        self.ctx.lam.update_function_configuration(
            FunctionName=self.ctx.fn.function_name,
            Environment={"Variables": set_env_var(original, var, bad)})
        self._wait_updated()
        return Injection(
            subtype="drift", root_cause_layer="CONFIG",
            root_cause_artifact=f"{self.ctx.fn.function_name}: environment variable {var}={bad}",
            artifact_match=[[var]],
            saved={"Variables": original}, details={"variable": var, "value": bad})

    def revert(self, saved):
        self.ctx.lam.update_function_configuration(FunctionName=self.ctx.fn.function_name,
                                                   Environment={"Variables": saved["Variables"]})
        self._wait_updated()


class Throttling(Fault):
    """F4 - reserved concurrency set to 1."""
    fault_type = "F4"

    def inject(self) -> Injection:
        n = self.ctx.cfg["faults"]["F4"]["reserved_concurrency"]
        prev = self.ctx.lam.get_function_concurrency(FunctionName=self.ctx.fn.function_name)
        saved = {"ReservedConcurrentExecutions": prev.get("ReservedConcurrentExecutions")}
        self.ctx.lam.put_function_concurrency(FunctionName=self.ctx.fn.function_name,
                                              ReservedConcurrentExecutions=n)
        return Injection(
            subtype="drift", root_cause_layer="CONFIG",
            root_cause_artifact=f"{self.ctx.fn.function_name}: ReservedConcurrentExecutions={n}",
            artifact_match=[["concurren"]],
            saved=saved, details={"reserved_concurrency": n})

    def revert(self, saved):
        prev = saved.get("ReservedConcurrentExecutions")
        if prev is None:
            self.ctx.lam.delete_function_concurrency(FunctionName=self.ctx.fn.function_name)
        else:
            self.ctx.lam.put_function_concurrency(FunctionName=self.ctx.fn.function_name,
                                                  ReservedConcurrentExecutions=prev)


class FaultyCommit(Fault):
    """F5 - commit a wrong value to the SAM template and deploy it (no drift)."""
    fault_type = "F5"

    def inject(self) -> Injection:
        cfg, fn_cfg = self.ctx.cfg, self.ctx.fn_cfg
        repo = cfg.app_repo
        tpl_name = cfg["app"]["template_file"]
        var, bad = fn_cfg["env_var"], fn_cfg["env_bad_value"]
        template = (repo / tpl_name).read_text(encoding="utf-8")
        new = edit_template_env_var(template, fn_cfg["logical_id"], var, bad)
        msg = cfg["faults"]["F5"]["commit_message"].format(env_var=var, function=self.ctx.fn.key)
        sha = apprepo.commit_file(repo, tpl_name, new, msg)
        try:
            apprepo.sam_deploy(cfg)
        except Exception:
            # not deployed: remove the commit again so the repository matches AWS
            apprepo.drop_last_commit(repo, sha)
            raise
        self._wait_updated()
        return Injection(
            subtype="committed", root_cause_layer="IAC",
            root_cause_artifact=f"commit {sha}: {var}={bad} in {tpl_name}",
            artifact_match=[[sha[:7]]],
            saved={"commit": sha}, details={"commit": sha, "variable": var, "value": bad})

    def revert(self, saved):
        apprepo.revert(self.ctx.cfg.app_repo, saved["commit"])
        apprepo.sam_deploy(self.ctx.cfg)
        self._wait_updated()


class SilentDrift(Fault):
    """F6 - add an unused permission; changes no behaviour (tests false alarms)."""
    fault_type = "F6"
    symptomatic = False

    def inject(self) -> Injection:
        action = self.ctx.cfg["faults"]["F6"]["extra_action"]
        original = self._get_policy()
        self._put_policy(add_unused_permission(original, action))
        self._iam_settle()
        return Injection(
            subtype="silent", root_cause_layer="NONE",
            root_cause_artifact=f"{self.ctx.fn.role_name}/{self._policy_name()}: unused {action} added",
            artifact_match=[], saved={"policy": original}, details={"action": action})

    def revert(self, saved):
        self._put_policy(saved["policy"])
        self._iam_settle()


FAULTS: dict[str, type[Fault]] = {
    cls.fault_type: cls
    for cls in (RemovePermission, LowerMemoryTimeout, WrongEnvVar, Throttling, FaultyCommit, SilentDrift)
}
