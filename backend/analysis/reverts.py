"""Detector: an edit the agent made was undone again."""

from __future__ import annotations

import re
from typing import Sequence

from backend.parser import Step
from backend.parser.utils import canonical

from .models import AnalysisConfig, Finding

__all__ = ["detect"]

EDIT_TOOLS = {"write", "write_file", "edit", "multiedit", "notebookedit", "replace", "apply_patch", "patch", "str_replace_editor"}
UNDO_TOOLS = {"undo", "revert", "rollback", "git_reset", "restore", "checkout"}
SHELL_TOOLS = {"bash", "shell", "run", "exec", "terminal", "run_command", "local_shell"}
_WHOLE_TREE = re.compile(r"git\s+(?:reset\s+--hard|stash\b|revert\b|checkout\s+--\s+\.|restore\s+\.)", re.IGNORECASE)
UNDO_COMMAND = re.compile(r"git\s+(?:checkout\s+--|restore\b|reset\s+--hard|revert\b|stash\b)", re.IGNORECASE)


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    edits: list[Step] = []
    findings: list[Finding] = []

    for step in steps:
        if not step.is_tool_call or not step.tool_name:
            continue
        tool = step.tool_name.lower()
        if _is_undo(tool, step):
            edit = _reverted_edit(edits, step)
            if edit:
                findings.append(Finding(
                    type="reverted_edit",
                    severity="medium",
                    steps=(edit.id, step.id),
                    message="An edit made by the agent appears to have been reverted.",
                    evidence={"undo_tool": step.tool_name, "edit_tool": edit.tool_name},
                ))
        elif tool in EDIT_TOOLS:
            edits.append(step)
    return findings


def _edited_file(step: Step) -> str | None:
    arguments = step.tool_arguments if isinstance(step.tool_arguments, dict) else {}
    for key in ("file_path", "path", "filename", "file", "notebook_path"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\\", "/").rsplit("/", 1)[-1]
    return None


def _reverted_edit(edits: Sequence[Step], undo: Step) -> Step | None:
    """The latest edit the undo plausibly refers to.

    When an edit names its file, the undo must mention that file - unless it is a
    whole-tree undo (``git reset --hard``, ``git stash``) that names no file at all.
    """
    if not edits:
        return None
    command = canonical(undo.tool_arguments)
    whole_tree = bool(_WHOLE_TREE.search(command)) or undo.tool_name.lower() not in SHELL_TOOLS
    for edit in reversed(edits):
        name = _edited_file(edit)
        if name is None or name in command:
            return edit
        if whole_tree:
            return edit
    return None


def _is_undo(tool: str, step: Step) -> bool:
    if tool in UNDO_TOOLS:
        return True
    return tool in SHELL_TOOLS and bool(UNDO_COMMAND.search(canonical(step.tool_arguments)))
