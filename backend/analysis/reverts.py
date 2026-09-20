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
UNDO_COMMAND = re.compile(r"git\s+(?:checkout\s+--|restore\b|reset\s+--hard|revert\b|stash\b)", re.IGNORECASE)


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    edits: list[Step] = []
    findings: list[Finding] = []

    for step in steps:
        if not step.is_tool_call or not step.tool_name:
            continue
        tool = step.tool_name.lower()
        if _is_undo(tool, step):
            if edits:
                findings.append(Finding(
                    type="reverted_edit",
                    severity="medium",
                    steps=(edits[-1].id, step.id),
                    message="An edit made by the agent appears to have been reverted.",
                    evidence={"undo_tool": step.tool_name, "edit_tool": edits[-1].tool_name},
                ))
        elif tool in EDIT_TOOLS:
            edits.append(step)
    return findings


def _is_undo(tool: str, step: Step) -> bool:
    if tool in UNDO_TOOLS:
        return True
    return tool in SHELL_TOOLS and bool(UNDO_COMMAND.search(canonical(step.tool_arguments)))
