"""Detector: failing tools, retries of a failed command, and session errors."""

from __future__ import annotations

from typing import Sequence

from backend.parser import Step
from backend.parser.utils import canonical

from .models import AnalysisConfig, Finding

__all__ = ["detect"]


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    calls_by_id = {step.call_id: step for step in steps if step.call_id and step.is_tool_call}
    failed: dict[tuple[str, str], int] = {}
    findings: list[Finding] = []

    for step in steps:
        if step.status != "error":
            continue
        call = calls_by_id.get(step.call_id) if step.call_id else None
        tool = step.tool_name or (call.tool_name if call else None)
        error = (step.error or "").strip()

        if not tool:
            findings.append(Finding(
                type="session_error",
                severity="high",
                steps=(step.id,),
                message="The session or turn ended with an error.",
                evidence={"error": error[:500]} if error else {},
            ))
            continue

        arguments = call.tool_arguments if call else step.tool_arguments
        key = (tool.lower(), canonical(arguments))
        previous = failed.get(key)
        anchor = call.id if call else step.id
        if previous is None:
            findings.append(Finding(
                type="tool_failure",
                severity="medium",
                steps=tuple(sorted({anchor, step.id})),
                message=f"Tool '{tool}' failed.",
                evidence={"tool": tool, "error": error[:500]} if error else {"tool": tool},
            ))
        else:
            findings.append(Finding(
                type="retry",
                severity="high",
                steps=(previous, step.id),
                message=f"Tool '{tool}' was run again after the same command had already failed.",
                evidence={"tool": tool, "error": error[:500]} if error else {"tool": tool},
            ))
        failed[key] = step.id
    return findings
