"""Read-only view of the benchmark application's git repository, pinned to the end of
an analysis window.

Pinning matters: commits made after the window (for example the `git revert` of an F5
fault) must not be visible to the agent. Only `git` read commands are executed, and
paths are restricted to files tracked at the pinned commit (Section 5.7).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

MAX_OUTPUT = 20_000


class GitView:
    def __init__(self, repo: Path, as_of_iso: str, branch: str = "main"):
        self.repo = Path(repo)
        self.commit = self._git("rev-list", "-1", f"--before={as_of_iso}", branch)
        if not self.commit:
            raise ValueError(f"no commit before {as_of_iso} in {repo}")

    def _git(self, *args: str) -> str:
        out = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=self.repo,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if out.returncode != 0:
            raise ValueError(out.stderr.strip() or "git command failed")
        return out.stdout.strip()

    @staticmethod
    def _clip(text: str) -> str:
        return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + "\n... [truncated]"

    def tracked_files(self) -> list[str]:
        return self._git("ls-tree", "-r", "--name-only", self.commit).splitlines()

    def read_file(self, path: str) -> str:
        path = path.replace("\\", "/").lstrip("/")
        if path not in self.tracked_files():
            raise ValueError(f"{path} is not a tracked file; available: {', '.join(self.tracked_files())}")
        return self._clip(self._git("show", f"{self.commit}:{path}"))

    def log(self, max_count: int = 20) -> str:
        max_count = max(1, min(int(max_count), 50))
        return self._git("log", f"--max-count={max_count}", "--date=iso-strict",
                         "--format=%h %ad %s", "--stat", self.commit)

    def show(self, commit: str) -> str:
        commit = commit.strip()
        if not commit.isalnum():
            raise ValueError("commit must be a hash")
        full = self._git("rev-parse", "--verify", f"{commit}^{{commit}}")
        # Only commits that existed at the pinned point in time.
        check = subprocess.run(["git", "merge-base", "--is-ancestor", full, self.commit], cwd=self.repo)
        if check.returncode != 0:
            raise ValueError(f"commit {commit} not found")
        return self._clip(self._git("show", "--date=iso-strict", "--format=commit %H%nDate: %ad%n%n    %s%n", full))
