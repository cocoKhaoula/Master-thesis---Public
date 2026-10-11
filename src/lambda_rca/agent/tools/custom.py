"""Custom tools (thesis Table 3.1): the IaC template file (L3) and the source code with
its git history (L4). Built per window, because they are pinned to the window end."""
from __future__ import annotations

from pathlib import Path

from .gitview import GitView


def build_custom_tools(groups: list[str], repo: Path, template_file: str, as_of_iso: str) -> list:
    if not groups:
        return []
    from strands import tool  # imported lazily so the rest of the package works without strands

    view = GitView(repo, as_of_iso)
    tools = []

    if "iac_template" in groups:
        @tool
        def read_iac_template() -> str:
            """Return the AWS SAM template of the application (the intended state of all
            functions, IAM roles and resources) as it was committed at the end of the window."""
            return view.read_file(template_file)
        tools.append(read_iac_template)

    if "code" in groups:
        @tool
        def list_commits(max_count: int = 20) -> str:
            """List the most recent commits of the application repository (hash, date,
            message and changed files), newest first.

            Args:
                max_count: number of commits to return (1-50).
            """
            return view.log(max_count)

        @tool
        def show_commit(commit: str) -> str:
            """Show the full diff and message of one commit of the application repository.

            Args:
                commit: commit hash (short or full) as printed by list_commits.
            """
            return view.show(commit)

        @tool
        def read_source_file(path: str) -> str:
            """Return the content of a file of the application repository, for example
            functions/crud_api/handler.py.

            Args:
                path: path of the file relative to the repository root.
            """
            return view.read_file(path)

        tools += [list_commits, show_commit, read_source_file]
    return tools
