"""Detector: the user had to step in and correct a working agent.

The opening request is the task itself, not an intervention, so only user turns
that arrive after the agent has already acted are counted.
"""

from __future__ import annotations

from typing import Sequence

from backend.parser import AGENT, USER, Step

from .models import AnalysisConfig, Finding

__all__ = ["detect"]


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    findings: list[Finding] = []
    agent_active = False

    for step in steps:
        if step.actor != USER:
            agent_active = agent_active or step.actor == AGENT
            continue
        if not agent_active:
            continue
        evidence: dict[str, object] = {"event_type": step.event_type}
        if step.text:
            evidence["message"] = step.text.strip()[:500]
        findings.append(Finding(
            type="human_intervention",
            severity="medium",
            steps=(step.id,),
            message="The user interrupted the agent to correct or redirect it.",
            evidence=evidence,
        ))
    return findings
