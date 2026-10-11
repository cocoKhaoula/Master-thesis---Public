"""Agent output schema (thesis Appendix C) and parsing of the model's answer.

Answers that cannot be parsed or that violate the schema are counted as a reported
anomaly with no valid candidate (Appendix C).
"""
from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

ANSWER_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AgentAnswer",
    "type": "object",
    "required": ["anomaly", "root_cause_layer", "function", "candidates", "explanation"],
    "additionalProperties": False,
    "properties": {
        "anomaly": {"type": "boolean"},
        "root_cause_layer": {"enum": ["IAM", "CONFIG", "IAC", "CODE", "NONE"]},
        "function": {"type": ["string", "null"]},
        "candidates": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "explanation": {"type": "string", "maxLength": 1500},
    },
    "allOf": [{
        "if": {"properties": {"anomaly": {"const": False}}},
        "then": {"properties": {"root_cause_layer": {"const": "NONE"},
                                "candidates": {"maxItems": 0}}},
    }],
}

INVALID_ANSWER = {"anomaly": True, "root_cause_layer": "NONE", "function": None,
                  "candidates": [], "explanation": ""}

_validator = jsonschema.Draft202012Validator(ANSWER_SCHEMA)


def _extract_json(text: str) -> str | None:
    """Take the JSON object from the answer, tolerating code fences or surrounding text."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_answer(text: str) -> tuple[dict[str, Any], bool, str | None]:
    """Return (answer, valid, error). Invalid answers are replaced by INVALID_ANSWER."""
    raw = _extract_json(text or "")
    if raw is None:
        return dict(INVALID_ANSWER), False, "no JSON object found"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return dict(INVALID_ANSWER), False, f"invalid JSON: {e}"
    errors = sorted(_validator.iter_errors(obj), key=lambda e: e.path)
    if errors:
        return dict(INVALID_ANSWER), False, "; ".join(e.message for e in errors[:3])
    return obj, True, None
