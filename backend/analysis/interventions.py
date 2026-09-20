"""Detector: the user had to step in and correct a working agent.

The opening request is the task itself, not an intervention, so only user turns
that arrive after the agent has already acted are counted.
"""

from __future__ import annotations

import re
from typing import Sequence

from backend.parser import AGENT, USER, Step

from .models import AnalysisConfig, Finding

__all__ = ["detect"]

# Wording that marks a user turn as a correction rather than the next request.
_CORRECTION = re.compile(
    r"\[request interrupted|\b(?:no|nope|stop|wrong|don'?t|do not|not what|revert|undo|"
    r"still (?:broken|fails?|failing|not)|didn'?t|doesn'?t work|that'?s not|screwed|broken?|"
    r"weird|bug|glitch|artefacts?|artifacts?|not working|isn'?t working|messed up|incorrect|why did you)\b|"
    r"(?<![а-яё])(?:нет|не так|не то|не надо|не нужно|стоп|неправильно|неверно|откати|верни|"
    r"опять|снова|всё ещё|все еще|не работает|зачем ты|я же (?:говорил|просил))(?![а-яё])",
    re.IGNORECASE,
)


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    findings: list[Finding] = []
    agent_active = False
    mid_work = False
    rejected_at: int | None = None

    for step in steps:
        if step.is_tool_result and step.status == "cancelled":
            findings.append(Finding(
                type="human_intervention",
                severity="medium",
                steps=(step.id,),
                message=f"The user rejected a '{step.tool_name or 'tool'}' call before it ran.",
                evidence={"event_type": "tool_rejected", **({"tool": step.tool_name} if step.tool_name else {})},
            ))
            rejected_at = step.id
        if step.actor != USER:
            if step.actor == AGENT:
                agent_active = True
                # A plain agent message ends its turn; anything tool-related
                # means the user cut in while work was still in flight.
                mid_work = step.is_tool_call or step.is_tool_result
            continue
        interrupted, mid_work = mid_work, False
        # The harness follows a rejection with its own "[Request interrupted..." turn;
        # that is the same event, not a second intervention.
        if rejected_at == step.id - 1 and (step.text or "").lstrip().lower().startswith("[request interrupted"):
            continue
        if not agent_active:
            continue
        correction = bool(_CORRECTION.search(step.text or ""))
        if not interrupted and not correction:
            continue
        evidence: dict[str, object] = {
            "event_type": step.event_type,
            "while_agent_was_working": interrupted,
            "correction_wording": correction,
        }
        if step.text:
            evidence["message"] = step.text.strip()[:500]
        findings.append(Finding(
            type="human_intervention",
            # Steering typed mid-work may be a nudge or an approval; a correction is
            # the costly kind - the agent's work so far was off.
            severity="medium" if correction else "low",
            steps=(step.id,),
            message=(
                "The user corrected the agent." if correction and not interrupted
                else "The user cut in with a correction while the agent was working." if correction
                else "The user sent a message while the agent was still working."
            ),
            evidence=evidence,
        ))
    return findings
