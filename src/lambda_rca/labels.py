"""Ground-truth label records (thesis Table 4.2) and the matching rules used for
root-cause evaluation (Section 2.6, Section 9.3 "Construct validity").

The matching rules are written into each label by the harness at injection time, i.e.
they are fixed before any agent run and applied automatically by the evaluation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Layer names used in labels and agent answers (Appendix C).
LAYERS = ("IAM", "CONFIG", "IAC", "CODE", "NONE")

FAULT_TYPES = {
    "F1": "remove_iam_permission",
    "F2": "lower_memory_timeout",
    "F3": "wrong_env_var",
    "F4": "throttling",
    "F5": "faulty_committed_change",
    "F6": "silent_drift",
    "N": "normal",
}

# Layers accepted as correct for Level-1 localisation, per fault type.
# A committed change is visible both in the IaC template and in the code history.
ACCEPTED_LAYERS = {
    "F1": ["IAM"],
    "F2": ["CONFIG"],
    "F3": ["CONFIG"],
    "F4": ["CONFIG"],
    "F5": ["IAC", "CODE"],
    "F6": ["NONE"],
    "N": ["NONE"],
}


@dataclass
class Label:
    incident_id: str
    start_time: str                 # UTC ISO-8601
    end_time: str
    fault_type: str                 # F1..F6 or N
    subtype: str                    # drift | committed | silent | none
    function: str | None
    root_cause_layer: str           # IAM | CONFIG | IAC | CODE | NONE
    root_cause_artifact: str | None
    # --- evaluation rules (not shown to the agent)
    symptomatic: bool = True
    accepted_layers: list[str] = field(default_factory=list)
    # Level-2 rule: a candidate matches if, for at least one inner list, all tokens occur
    # in the normalised candidate text. Example: [["putitem"]] or [["memory"], ["timeout"]].
    artifact_match: list[list[str]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Label":
        return cls(**d)

    def window_record(self) -> dict[str, Any]:
        """What the agent runner may see: identifier and time range only (Section 3.7)."""
        return {"window_id": self.incident_id, "start": self.start_time, "end": self.end_time}


def normalise(text: str) -> str:
    """Lower-case and drop characters that differ between equivalent spellings."""
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == "_")


def artifact_matches(candidate: str, rules: list[list[str]]) -> bool:
    c = normalise(candidate)
    return any(rule and all(normalise(tok) in c for tok in rule) for rule in rules)
