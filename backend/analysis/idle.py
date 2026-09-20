"""Detector: long gaps between recorded steps."""

from __future__ import annotations

from typing import Sequence

from backend.parser import Step

from .models import AnalysisConfig, Finding

__all__ = ["detect"]


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    timed = [step for step in steps if step.timestamp]
    findings: list[Finding] = []

    for before, after in zip(timed, timed[1:]):
        seconds = (after.timestamp - before.timestamp).total_seconds()
        if seconds < config.idle_seconds:
            continue
        findings.append(Finding(
            type="idle_period",
            severity="high" if seconds >= config.idle_seconds * config.idle_high_multiplier else "low",
            steps=(before.id, after.id),
            message=f"{seconds:.0f}s elapsed between recorded steps.",
            evidence={"duration_seconds": round(seconds, 1)},
        ))
    return findings
