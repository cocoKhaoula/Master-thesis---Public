"""Command-line entry point: `lambda-rca <command>`. See README.md for the full workflow."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import LEVELS, Config


def _levels(s: str | None) -> list[str]:
    if not s:
        return list(LEVELS)
    levels = [x.strip().upper() for x in s.split(",")]
    bad = [l for l in levels if l not in LEVELS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown level(s): {bad}")
    return levels


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lambda-rca", description=__doc__)
    p.add_argument("--config", help="path to experiment.yaml (default: config/experiment.yaml)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-app-repo", help="create the benchmark app's git repository from ./app")
    s.add_argument("--force", action="store_true")
    sub.add_parser("deploy", help="sam build + sam deploy of the app repository (harness profile)")
    sub.add_parser("seed", help="upload input objects for the benchmark functions")
    s = sub.add_parser("loadgen", help="run the constant-rate load generator")
    s.add_argument("--minutes", type=float)
    s = sub.add_parser("steady-state", help="record the fault-free training period for Isolation Forest")
    s.add_argument("--minutes", type=int)
    sub.add_parser("plan", help="print the planned windows")

    s = sub.add_parser("campaign", help="run the fault injection campaign")
    s.add_argument("--limit", type=int, help="run at most N windows (pilot)")
    s.add_argument("--only", help="comma-separated window ids")
    s.add_argument("--no-agent", action="store_true", help="do not run the agent in hold mode")
    s.add_argument("--levels", help="levels to run in hold mode (default: all)")
    s.add_argument("--reps", type=int)
    s.add_argument("--ttd", action="store_true", help="also run agent time-to-detect polling runs")
    s.add_argument("--ttd-levels", default="L1,L4")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("recover", help="revert a fault left active by an interrupted campaign")

    s = sub.add_parser("run-agent", help="run the agent on recorded windows (only valid while the fault is "
                                         "active, or for normal windows; see README)")
    s.add_argument("--levels")
    s.add_argument("--window", help="window id (default: all windows)")
    s.add_argument("--reps", type=int)

    sub.add_parser("baselines", help="apply threshold, Isolation Forest and drift baselines")
    sub.add_parser("evaluate", help="compute metrics and write results/")
    sub.add_parser("plots", help="draw the Chapter 7 figures from results/")
    s = sub.add_parser("show-tools", help="list the tools the agent receives at each level")
    s.add_argument("--levels")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("botocore", "urllib3", "httpx", "mcp", "strands"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = Config.load(args.config)

    if args.cmd == "init-app-repo":
        from .harness.apprepo import init_app_repo
        print(init_app_repo(cfg, force=args.force))
    elif args.cmd == "deploy":
        from .harness.apprepo import sam_deploy
        sam_deploy(cfg)
    elif args.cmd == "seed":
        from .harness.loadgen import seed_inputs
        seed_inputs(cfg)
    elif args.cmd == "loadgen":
        from .harness.loadgen import LoadGenerator
        LoadGenerator(cfg).run(args.minutes)
    elif args.cmd == "steady-state":
        from .harness.campaign import Campaign
        print(Campaign(cfg).steady_state(args.minutes))
    elif args.cmd == "plan":
        from collections import Counter
        from .harness.campaign import plan_windows
        plan = plan_windows(cfg)
        for w in plan:
            print(w.window_id, w.fault_type, w.function or "-", w.repetition)
        print(dict(Counter(w.fault_type for w in plan)), "total", len(plan))
    elif args.cmd == "campaign":
        from .harness.campaign import Campaign
        analyse = None
        if not args.no_agent and not args.dry_run:
            from .agent.runner import AgentRunner
            runner = AgentRunner(cfg)
            levels = _levels(args.levels)

            def analyse(window):
                runner.run_window(window, levels, args.reps)
                if args.ttd:
                    runner.run_ttd(window, _levels(args.ttd_levels))
        Campaign(cfg, analyse=analyse, dry_run=args.dry_run).run(
            only=args.only.split(",") if args.only else None, limit=args.limit)
    elif args.cmd == "recover":
        from .harness.campaign import Campaign
        print("reverted" if Campaign(cfg).recover() else "nothing to recover")
    elif args.cmd == "run-agent":
        from .agent.runner import AgentRunner
        from .io import read_jsonl
        runner = AgentRunner(cfg)
        windows = [w for w in read_jsonl(cfg.path("windows_file")) if not args.window or w["window_id"] == args.window]
        for w in windows:
            runner.run_window(w, _levels(args.levels), args.reps)
    elif args.cmd == "baselines":
        from .baselines.run import run_baselines
        run_baselines(cfg)
    elif args.cmd == "evaluate":
        from .evaluation.evaluate import evaluate
        t = evaluate(cfg)
        print(t["summary"].to_string(index=False))
    elif args.cmd == "plots":
        from .evaluation.plots import plot_all
        plot_all(cfg)
    elif args.cmd == "show-tools":
        from contextlib import ExitStack
        from .agent.runner import _allowed, _mcp_client, _tool_name
        blocked = cfg.levels_raw.get("blocked_tool_prefixes", [])
        for level in _levels(args.levels):
            lvl = cfg.level(level)
            names = []
            with ExitStack() as stack:
                for name in lvl.get("mcp", []):
                    client = stack.enter_context(_mcp_client(cfg.levels_raw["mcp_servers"][name], cfg))
                    for t in client.list_tools_sync():
                        n = _tool_name(t)
                        names.append(f"{name}:{n}" + ("" if _allowed(n, blocked) else "  [blocked]"))
            for g in lvl.get("custom", []):
                names += [f"custom:{t}" for t in cfg.levels_raw["custom_tools"][g]]
            print(f"{level} ({lvl['description']}):")
            for n in names or ["(no tools; raw logs in prompt)"]:
                print("   ", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
