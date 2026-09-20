"""Detector: the same tool called again with (nearly) the same arguments."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Sequence

from backend.parser import Step
from backend.parser.utils import canonical

from .models import AnalysisConfig, Finding

__all__ = ["detect"]


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    history: dict[str, list[tuple[int, str]]] = {}
    findings: list[Finding] = []

    for step in steps:
        if not step.tool_name or not step.is_tool_call:
            continue
        key = step.tool_name.lower()
        signature = canonical(step.tool_arguments)
        for previous_id, previous_signature in history.get(key, [])[-config.repeat_window:]:
            ratio = SequenceMatcher(None, previous_signature, signature).ratio()
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


def _short(value: str, limit: int = 200) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"
