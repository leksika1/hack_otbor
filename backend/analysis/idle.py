"""Detector: long gaps between recorded steps."""

from __future__ import annotations

from typing import Sequence

from backend.parser import SYSTEM, USER, Step

from .models import AnalysisConfig, Finding

__all__ = ["detect"]


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    timed = [step for step in steps if step.timestamp]
    findings: list[Finding] = []
    background_waits: list[tuple[float, int, int]] = []

    for before, after in zip(timed, timed[1:]):
        seconds = (after.timestamp - before.timestamp).total_seconds()
        if seconds < config.idle_seconds:
            continue
        # A gap that ends with a user turn is the human reading or typing,
        # not the agent stalling.
        if after.actor == USER:
            continue
        if after.actor == SYSTEM:
            # The agent had ended its turn. Waiting for a background task is worth
            # showing (as information, never "high"); anything else is the human away.
            if after.event_type == "task_notification":
                background_waits.append((seconds, before.id, after.id))
            continue
        slow_tool = before.is_tool_call and after.is_tool_result and before.call_id == after.call_id
        evidence: dict[str, object] = {"duration_seconds": round(seconds, 1)}
        if slow_tool:
            evidence.update(waiting_on="tool", tool=before.tool_name)
        findings.append(Finding(
            type="idle_period",
            severity="high" if seconds >= config.idle_seconds * config.idle_high_multiplier else "low",
            steps=(before.id, after.id),
            message=(
                f"Tool '{before.tool_name}' took {seconds:.0f}s to return."
                if slow_tool else f"{seconds:.0f}s elapsed between recorded steps."
            ),
            evidence=evidence,
        ))
    if background_waits:
        # One finding for the whole pattern: ten separate "waited 5 minutes" lines
        # bury the point, which is the total.
        total = sum(wait[0] for wait in background_waits)
        longest = sorted(background_waits, reverse=True)[:3]
        findings.append(Finding(
            type="idle_period",
            severity="medium" if total >= 1800 else "low",
            steps=tuple(sorted({step_id for _, start, end in longest for step_id in (start, end)})),
            message=(
                f"The agent sat idle waiting for background tasks {len(background_waits)} time(s), "
                f"{total / 60:.0f} min in total (longest {longest[0][0] / 60:.0f} min)."
            ),
            evidence={"waiting_on": "background_task", "occurrences": len(background_waits),
                      "duration_seconds": round(total, 1), "longest_seconds": round(longest[0][0], 1)},
        ))
    return findings
