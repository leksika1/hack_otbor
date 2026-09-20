"""Detector: the same tool called again with (nearly) the same arguments."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Sequence

from backend.parser import Step
from backend.parser.utils import canonical

from .models import AnalysisConfig, Finding

__all__ = ["detect"]

_COMPARE_LIMIT = 1500
_IDENTITY_KEYS = ("file_path", "path", "notebook_path", "url", "pattern", "query", "offset", "limit",
                  "subagent_type", "skill", "task_id")
# Anonymized logs number every placeholder occurrence ([USER_170], [USER_198]):
# the same path would otherwise never compare equal.
_ANONYMIZED = re.compile(r"\[([A-Z][A-Z_]*?)_\d+\]")
_TOKEN = re.compile(r"[^\s\"'\\,:=(){}\[\]]+")
_TARGET_LIKE = re.compile(r"[/.\d_-]")
_POLLING_TOOLS = {"taskoutput", "bashoutput", "monitor", "wait", "sleep", "todowrite", "todoread"}
_POLLING_ACTIONS = {"wait", "screenshot", "zoom", "scroll"}


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    history: dict[str, list[tuple[int, str]]] = {}
    findings: list[Finding] = []

    for step in steps:
        if not step.tool_name or not step.is_tool_call or _is_polling(step):
            continue
        key = step.tool_name.lower() + _identity(step.tool_arguments)
        signature = _ANONYMIZED.sub(r"[\1]", canonical(step.tool_arguments))
        for previous_id, previous_signature in history.get(key, [])[-config.repeat_window:]:
            ratio = _similarity(previous_signature, signature, config.similarity_threshold)
            if ratio < 1.0 and _different_target(previous_signature, signature):
                continue
            if ratio >= config.similarity_threshold:
                identical = ratio == 1.0
                findings.append(Finding(
                    type="repeated_tool_call",
                    severity="high" if identical else "medium",
                    steps=(previous_id, step.id),
                    message=(
                        f"Tool '{step.tool_name}' repeated with "
                        f"{'identical' if identical else 'very similar'} arguments."
                    ),
                    evidence={
                        "tool": step.tool_name,
                        "similarity": round(ratio, 3),
                        "arguments": _short(signature),
                    },
                ))
                break
        history.setdefault(key, []).append((step.id, signature))
    return findings


def _different_target(left: str, right: str) -> bool:
    """Same command template aimed at another file, task or parameter.

    ``run V2A_TASK.md`` and ``run V2B_TASK.md`` are 95% similar as text and are
    still two different jobs: a token that differs and looks like a path, a file
    name or a number means the call was not a repeat.
    """
    left_tokens, right_tokens = set(_TOKEN.findall(left)), set(_TOKEN.findall(right))
    return any(_TARGET_LIKE.search(token) for token in left_tokens ^ right_tokens)


def _identity(arguments: object) -> str:
    """Arguments that name WHAT is touched. Similar paths are not the same file."""
    if not isinstance(arguments, dict):
        return ""
    parts = [name + "=" + _ANONYMIZED.sub(r"[\1]", str(arguments[name]))
             for name in _IDENTITY_KEYS if isinstance(arguments.get(name), (str, int))]
    return "|" + "|".join(parts) if parts else ""


def _is_polling(step: Step) -> bool:
    """Waiting, screenshots and status checks repeat by design - not a wasted call."""
    if step.tool_name.lower() in _POLLING_TOOLS:
        return True
    arguments = step.tool_arguments if isinstance(step.tool_arguments, dict) else {}
    return str(arguments.get("action", "")).lower() in _POLLING_ACTIONS


def _similarity(left: str, right: str, threshold: float) -> float:
    """SequenceMatcher.ratio(), skipped whenever a cheap bound already rules a match out."""
    if left == right:
        return 1.0
    longest = max(len(left), len(right))
    if not longest or 2 * min(len(left), len(right)) / (len(left) + len(right)) < threshold:
        return 0.0
    # Large file bodies dominate the cost; the head is enough to tell edits apart.
    matcher = SequenceMatcher(None, left[:_COMPARE_LIMIT], right[:_COMPARE_LIMIT])
    if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
        return 0.0
    return matcher.ratio()


def _short(value: str, limit: int = 200) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
