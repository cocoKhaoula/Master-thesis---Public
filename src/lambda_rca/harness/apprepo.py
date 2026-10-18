"""The benchmark application's own git repository and its SAM deployment.

Every change to the intended state is a commit in this repository (Section 3.4). The
harness commits faulty values here for F5, and the agent's code tool reads its history.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..config import Config

BENIGN_NOTES = [
    "Clarify cart payload format in README",
    "Document thumbnail size defaults",
    "Note compression level choice",
    "Describe uploader timeout behaviour",
    "Add load-test notes",
]


def _git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True)
    return out.stdout.strip()


def init_app_repo(cfg: Config, force: bool = False) -> Path:
    """Copy ./app into the working repository and make the initial commit."""
    repo = cfg.app_repo
    if repo.exists():
        if not force:
            raise FileExistsError(f"{repo} exists; use --force to recreate it")
        shutil.rmtree(repo)
    shutil.copytree(cfg.root / "app", repo, ignore=shutil.ignore_patterns(".aws-sam", "__pycache__"))
    (repo / "README.md").write_text(
        "# lambda-rca-bench\n\nSeBS functions deployed with AWS SAM.\n\n## Notes\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".aws-sam/\n__pycache__/\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "lambda-rca-bench")
    _git(repo, "config", "user.email", "bench@example.invalid")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Initial benchmark application (SeBS functions, SAM template)")
    return repo


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def commit_file(repo: Path, relpath: str, content: str, message: str) -> str:
    (repo / relpath).write_text(content, encoding="utf-8", newline="")
    _git(repo, "add", relpath)
    _git(repo, "commit", "-m", message)
    return head(repo)


def revert(repo: Path, commit: str) -> str:
    _git(repo, "revert", "--no-edit", commit)
    return head(repo)


def benign_commit(repo: Path, n: int) -> str:
    """Documentation-only commit so that the history the agent reads is not trivially
    'the last commit is the fault'."""
    note = BENIGN_NOTES[n % len(BENIGN_NOTES)]
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + f"- {note}.\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", note)
    return head(repo)


def _sam_env() -> dict:
    """SAM builds Python functions with a local interpreter of the same version as the
    runtime (python3.12) and needs the SAM and AWS CLIs; background processes may start
    without them on PATH."""
    import os
    import shutil
    env = dict(os.environ)
    extra = []
    if not shutil.which("python3.12"):
        for d in [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312"), r"C:\Python312"]:
            if os.path.exists(os.path.join(d, "python.exe")):
                extra.append(d)
                break
    for d in [r"C:\Program Files\Amazon\AWSSAMCLI\bin", r"C:\Program Files\Amazon\AWSCLIV2"]:
        if os.path.isdir(d):
            extra.append(d)
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env["SAM_CLI_TELEMETRY"] = "0"
    return env


def sam_deploy(cfg: Config) -> None:
    """Build and deploy the working repository with the harness profile."""
    repo = cfg.app_repo
    env = _sam_env()
    common = ["--region", cfg.region, "--profile", cfg["aws"]["harness_profile"]]
    subprocess.run(["sam", "build", "--cached"], cwd=repo, check=True, shell=_shell(), env=env)
    subprocess.run(["sam", "deploy", "--stack-name", cfg.stack_name, "--capabilities", "CAPABILITY_IAM",
                    "--resolve-s3", "--no-confirm-changeset", "--no-fail-on-empty-changeset", *common],
                   cwd=repo, check=True, shell=_shell(), env=env)


def drop_last_commit(repo: Path, commit: str) -> None:
    """Remove a commit that was never deployed (used when a deployment fails)."""
    if head(repo) == commit:
        _git(repo, "reset", "--hard", f"{commit}~1")


def _shell() -> bool:
    # sam is a .cmd wrapper on Windows and needs the shell to be found.
    import os
    return os.name == "nt"
