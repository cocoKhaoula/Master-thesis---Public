"""Loading of config/experiment.yaml and config/ablation_levels.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "experiment.yaml"
DEFAULT_LEVELS = REPO_ROOT / "config" / "ablation_levels.yaml"

LEVELS = ("L0", "L1", "L2", "L3", "L4")


@dataclass
class Config:
    raw: dict[str, Any]
    levels_raw: dict[str, Any]
    root: Path = REPO_ROOT

    @classmethod
    def load(cls, path: str | os.PathLike | None = None,
             levels_path: str | os.PathLike | None = None) -> "Config":
        path = Path(path or os.environ.get("LAMBDA_RCA_CONFIG", DEFAULT_CONFIG))
        levels_path = Path(levels_path or DEFAULT_LEVELS)
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        with open(levels_path, encoding="utf-8") as f:
            levels_raw = yaml.safe_load(f)
        return cls(raw=raw, levels_raw=levels_raw)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    # ------------------------------------------------------------------ helpers
    @property
    def region(self) -> str:
        return self.raw["aws"]["region"]

    @property
    def stack_name(self) -> str:
        return self.raw["aws"]["stack_name"]

    @property
    def functions(self) -> dict[str, dict[str, Any]]:
        return self.raw["functions"]

    def path(self, key: str) -> Path:
        """Absolute path for an entry of the `paths` section."""
        return self.root / self.raw["paths"][key]

    @cached_property
    def app_repo(self) -> Path:
        return self.root / self.raw["app"]["repo_dir"]

    def level(self, name: str) -> dict[str, Any]:
        if name not in self.levels_raw["levels"]:
            raise KeyError(f"unknown ablation level {name}; expected one of {LEVELS}")
        return self.levels_raw["levels"][name]
