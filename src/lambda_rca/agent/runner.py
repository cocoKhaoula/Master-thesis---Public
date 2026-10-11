"""Agent runner: one ReAct agent run per (window, ablation level, repetition).

The agent is a Strands Agents `Agent` with a Claude model on Amazon Bedrock at
temperature 0 (Section 2.4). The tools are the MCP servers and custom tools of the
ablation level (config/ablation_levels.yaml); nothing else differs between levels.
For every run the JSON answer, the tool-call sequence, the token usage and the latency
are stored (requirements R5, R6) in data/runs/<level>/<window_id>_r<rep>.json.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..aws import resolve_functions, session
from ..config import LEVELS, Config
from ..io import iso, parse_iso, read_jsonl, utcnow, write_json
from .prompt import SYSTEM_PROMPT, user_message
from .rawlogs import collect_raw_logs
from .schema import parse_answer
from .tools.custom import build_custom_tools

log = logging.getLogger(__name__)


def _mcp_client(server: dict[str, Any], cfg: Config):
    from mcp import StdioServerParameters, stdio_client
    from strands.tools.mcp import MCPClient

    env = dict(os.environ)
    # MCP servers run with the read-only agent role's credentials (Section 5.7).
    env.update({"AWS_PROFILE": cfg["aws"]["agent_profile"], "AWS_REGION": cfg.region,
                "FASTMCP_LOG_LEVEL": "ERROR"})
    env.pop("AWS_ACCESS_KEY_ID", None)
    env.pop("AWS_SECRET_ACCESS_KEY", None)
    env.pop("AWS_SESSION_TOKEN", None)
    params = StdioServerParameters(command=server["command"], args=server["args"], env=env)
    return MCPClient(lambda: stdio_client(params))


def _tool_name(t) -> str:
    return getattr(t, "tool_name", None) or t.tool_spec["name"]


def _allowed(name: str, blocked_prefixes: list[str]) -> bool:
    n = name.lower()
    return not any(n.startswith(p + "_") or n == p for p in blocked_prefixes)


def _tool_calls(messages: list[dict]) -> list[dict]:
    """Ordered list of tool calls with a short preview of each result."""
    calls, results = [], {}
    for m in messages:
        for block in m.get("content", []):
            if "toolUse" in block:
                tu = block["toolUse"]
                calls.append({"id": tu.get("toolUseId"), "name": tu.get("name"), "input": tu.get("input")})
            elif "toolResult" in block:
                tr = block["toolResult"]
                text = " ".join(c.get("text", "") for c in tr.get("content", []) if isinstance(c, dict))
                results[tr.get("toolUseId")] = {"status": tr.get("status"), "preview": text[:500],
                                                "chars": len(text)}
    for c in calls:
        c["result"] = results.get(c["id"])
    return calls


class AgentRunner:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.levels = cfg.levels_raw
        self.functions = resolve_functions(cfg, "agent")
        self.agent_session = session(cfg, "agent")

    def run_path(self, level: str, window_id: str, rep: int, suffix: str = "") -> Path:
        return self.cfg.path("runs_dir") / level / f"{window_id}{suffix}_r{rep}.json"

    def run_once(self, level: str, window: dict, rep: int, out: Path | None = None) -> dict:
        from strands import Agent
        from strands.models import BedrockModel

        out = out or self.run_path(level, window["window_id"], rep)
        if out.exists():
            log.info("skip %s (exists)", out.name)
            return {}
        lvl = self.cfg.level(level)
        a = self.cfg["agent"]

        raw_logs = None
        if lvl.get("raw_logs_in_prompt"):
            raw_logs = collect_raw_logs(self.agent_session.client("logs"), self.functions,
                                        window["start"], window["end"], a["max_log_chars_l0"])
        prompt = user_message(window, self.cfg["app"]["id"], self.cfg.region,
                              [f.function_name for f in self.functions.values()], raw_logs)

        model = BedrockModel(boto_session=self.agent_session, model_id=a["model_id"],
                             temperature=a["temperature"], max_tokens=a["max_tokens"])
        blocked = self.levels.get("blocked_tool_prefixes", [])
        started = utcnow()
        t0 = time.perf_counter()
        error = None
        text, usage, messages, tool_names = "", {}, [], []
        with ExitStack() as stack:
            tools = []
            for name in lvl.get("mcp", []):
                client = stack.enter_context(_mcp_client(self.levels["mcp_servers"][name], self.cfg))
                tools += [t for t in client.list_tools_sync() if _allowed(_tool_name(t), blocked)]
            groups = [g for g in lvl.get("custom", [])]
            tools += build_custom_tools(groups, self.cfg.app_repo, self.cfg["app"]["template_file"], window["end"])
            tool_names = sorted(_tool_name(t) for t in tools)
            agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT, callback_handler=None)
            try:
                result = agent(prompt)
                text = str(result)
                usage = dict(result.metrics.accumulated_usage)
            except Exception as e:  # recorded, counted as invalid answer
                log.exception("agent run failed")
                error = repr(e)
            messages = list(agent.messages)
        latency = time.perf_counter() - t0

        answer, valid, parse_error = parse_answer(text)
        record = {
            "window_id": window["window_id"], "level": level, "repetition": rep,
            "window": window, "model_id": a["model_id"], "temperature": a["temperature"],
            "started": iso(started), "latency_s": round(latency, 2),
            "answer": answer, "valid": valid, "parse_error": parse_error, "error": error,
            "raw_text": text,
            "usage": {"input_tokens": usage.get("inputTokens", 0), "output_tokens": usage.get("outputTokens", 0),
                      "total_tokens": usage.get("totalTokens", 0)},
            "tools_available": tool_names,
            "tool_calls": _tool_calls(messages),
            "prompt_chars": len(prompt),
        }
        write_json(out, record)
        log.info("%s %s r%d -> anomaly=%s layer=%s valid=%s tokens=%s", window["window_id"], level, rep,
                 answer["anomaly"], answer["root_cause_layer"], valid, record["usage"]["total_tokens"])
        return record

    def run_window(self, window: dict, levels: list[str] | None = None, reps: int | None = None) -> None:
        levels = levels or list(LEVELS)
        reps = reps or self.cfg["agent"]["repetitions"]
        jobs = [(lvl, r) for r in range(1, reps + 1) for lvl in levels]
        with ThreadPoolExecutor(max_workers=self.cfg["agent"]["parallel_runs"]) as pool:
            for f in [pool.submit(self.run_once, lvl, window, r) for lvl, r in jobs]:
                f.result()

    def run_ttd(self, window: dict, levels: list[str]) -> None:
        """Time-to-detect runs (eq. 2.5): the agent is asked about growing prefixes of the
        window, at the configured polling interval, one repetition each."""
        poll = self.cfg["agent"]["ttd_poll_minutes"]
        start, end = parse_iso(window["start"]), parse_iso(window["end"])
        k = 1
        while start + timedelta(minutes=poll * k) <= end:
            sub = dict(window, end=iso(start + timedelta(minutes=poll * k)))
            for lvl in levels:
                self.run_once(lvl, sub, 1, self.run_path(lvl, window["window_id"], 1, suffix=f"_ttd{poll * k:02d}"))
            k += 1

    def run_all(self, levels: list[str] | None = None, reps: int | None = None) -> None:
        for window in read_jsonl(self.cfg.path("windows_file")):
            self.run_window(window, levels, reps)
