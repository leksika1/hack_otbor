"""Detector: parts of the session that burn far more tokens than the rest.

Deliberately simple and explainable: a bucket of steps is a hotspot when it uses
more than ``hotspot_ratio`` times the average bucket. Logs without usage data
produce no findings instead of guesses.
"""

from __future__ import annotations

from typing import Any, Sequence

from backend.parser import Step

from .models import AnalysisConfig, Finding

__all__ = ["detect", "build_buckets"]


def build_buckets(steps: Sequence[Step], bucket_size: int) -> list[dict[str, Any]]:
    size = max(1, bucket_size)
    buckets: list[dict[str, Any]] = []
    for start in range(0, len(steps), size):
        chunk = steps[start:start + size]
        if not chunk:
            continue
        buckets.append({
            "from_step": chunk[0].id,
            "to_step": chunk[-1].id,
            "tokens": sum(step.tokens for step in chunk),
            "cost": round(sum(step.cost for step in chunk), 6),
        })
    return buckets


def detect(steps: Sequence[Step], config: AnalysisConfig) -> list[Finding]:
    buckets = build_buckets(steps, config.bucket_size)
    total = sum(bucket["tokens"] for bucket in buckets)
    if len(buckets) < 2 or total <= 0:
        return []

    average = total / len(buckets)
    findings: list[Finding] = []
    for bucket in buckets:
        tokens = bucket["tokens"]
        ratio = tokens / average
        if ratio <= config.hotspot_ratio:
            continue
        findings.append(Finding(
            type="token_hotspot",
            severity="medium",
            steps=(bucket["from_step"], bucket["to_step"]),
            message=(
                f"Steps {bucket['from_step']}-{bucket['to_step']} used {tokens} tokens "
                f"({ratio:.1f}x the session average)."
            ),
            evidence={
                **({"cost_usd": bucket["cost"]} if bucket["cost"] else {}),
                "token_count": tokens,
                "average_bucket_tokens": round(average, 1),
                "ratio": round(ratio, 2),
            },
        ))
    return findings
