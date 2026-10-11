import subprocess
import time
from datetime import datetime, timezone

import pytest

from lambda_rca.agent.tools.gitview import GitView


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    (tmp_path / "template.yaml").write_text("TABLE_NAME: good\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "initial")
    time.sleep(1.1)
    (tmp_path / "template.yaml").write_text("TABLE_NAME: missing-table\n")
    git(tmp_path, "commit", "-am", "Update TABLE_NAME")
    fault = git(tmp_path, "rev-parse", "HEAD")
    time.sleep(1.1)
    window_end = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    time.sleep(1.1)
    git(tmp_path, "revert", "--no-edit", "HEAD")
    revert = git(tmp_path, "rev-parse", "HEAD")
    return tmp_path, fault, revert, window_end


def test_view_is_pinned_to_window_end(repo):
    path, fault, revert, end = repo
    view = GitView(path, end)
    assert view.commit == fault
    assert "missing-table" in view.read_file("template.yaml")
    assert "Revert" not in view.log()
    assert "missing-table" in view.show(fault[:7])
    with pytest.raises(ValueError):
        view.show(revert[:7])           # commit after the window is invisible


def test_paths_restricted(repo):
    path, _, _, end = repo
    view = GitView(path, end)
    with pytest.raises(ValueError):
        view.read_file("../secret.txt")
    with pytest.raises(ValueError):
        view.show("HEAD; rm -rf /")
