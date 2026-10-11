"""Raw log collection for level L0: all log events of the application in the window,
interleaved by time and truncated to a fixed character budget."""
from __future__ import annotations

from ..aws import FunctionResources
from ..io import parse_iso


def collect_raw_logs(logs_client, functions: dict[str, FunctionResources], start_iso: str, end_iso: str,
                     max_chars: int) -> str:
    start_ms = int(parse_iso(start_iso).timestamp() * 1000)
    end_ms = int(parse_iso(end_iso).timestamp() * 1000)
    events = []
    for key, fn in functions.items():
        paginator = logs_client.get_paginator("filter_log_events")
        try:
            for page in paginator.paginate(logGroupName=fn.log_group, startTime=start_ms, endTime=end_ms):
                for e in page["events"]:
                    events.append((e["timestamp"], fn.function_name, e["message"].rstrip()))
        except logs_client.exceptions.ResourceNotFoundException:
            continue
    events.sort()

    lines, used = [], 0
    for ts, name, msg in events:
        line = f"{ts} {name} {msg}"
        if used + len(line) + 1 > max_chars:
            lines.append(f"... [{len(events) - len(lines)} more events truncated]")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) if lines else "(no log events)"
