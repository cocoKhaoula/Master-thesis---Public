"""Pure functions that transform IAM policy documents and templates.

Kept free of AWS calls so that they can be unit-tested (tests/test_policy.py).
"""
from __future__ import annotations

import copy
import re
from typing import Any

SILENT_SID = "SilentDriftExtra"


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else [v]


def remove_action(doc: dict[str, Any], action: str) -> dict[str, Any]:
    """Return a copy of `doc` without `action` (F1). Statements left empty are dropped."""
    new = copy.deepcopy(doc)
    found = False
    statements = []
    for st in _as_list(new.get("Statement", [])):
        actions = _as_list(st.get("Action", []))
        kept = [a for a in actions if a.lower() != action.lower()]
        if len(kept) != len(actions):
            found = True
        if not kept:
            continue
        st["Action"] = kept if len(kept) > 1 else kept[0]
        statements.append(st)
    if not found:
        raise ValueError(f"action {action} not present in policy")
    new["Statement"] = statements
    return new


def add_unused_permission(doc: dict[str, Any], action: str) -> dict[str, Any]:
    """Return a copy of `doc` with an extra, unused Allow statement (F6, silent drift)."""
    new = copy.deepcopy(doc)
    statements = _as_list(new.get("Statement", []))
    statements.append({"Sid": SILENT_SID, "Effect": "Allow", "Action": action, "Resource": "*"})
    new["Statement"] = statements
    return new


def set_env_var(variables: dict[str, str], name: str, value: str) -> dict[str, str]:
    """update_function_configuration replaces the whole set of variables (Appendix A),
    so the complete original set is returned with one value changed."""
    if name not in variables:
        raise ValueError(f"environment variable {name} not set on the function")
    new = dict(variables)
    new[name] = value
    return new


def edit_template_env_var(template: str, logical_id: str, env_var: str, value: str) -> str:
    """Replace `env_var`'s value inside the resource block `logical_id` of a SAM template (F5).

    Works on the text so that the rest of the file, including comments and intrinsic
    functions such as !Ref, stays byte-identical and the commit diff is one line.
    """
    lines = template.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(rf"^  {re.escape(logical_id)}:\s*$", l)), None)
    if start is None:
        raise ValueError(f"resource {logical_id} not found in template")
    for i in range(start + 1, len(lines)):
        if re.match(r"^  \S", lines[i]):          # next top-level resource
            break
        m = re.match(rf"^(\s+){re.escape(env_var)}:\s*.*?(\r?\n)?$", lines[i])
        if m:
            lines[i] = f"{m.group(1)}{env_var}: {value}{m.group(2) or ''}"
            return "".join(lines)
    raise ValueError(f"{env_var} not found in resource {logical_id}")
