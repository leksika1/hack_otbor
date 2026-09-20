"""Example issues for local checks, demo and tests.

These mirror what the deterministic analyzers are expected to emit.
"""

from __future__ import annotations

from .schemas import Issue

__all__ = ["EXAMPLE_ISSUES", "example_issues"]

EXAMPLE_ISSUE_DICTS: list[dict] = [
    {
        "type": "repeated_tool_call",
        "severity": "high",
        "steps": [42, 43, 44, 45],
        "evidence": {"tool": "grep", "count": 4, "args": "UserService"},
        "context": (
            "The agent executed the same repository search four times with "
            "nearly identical arguments."
        ),
    },
    {
        "type": "tool_failure",
        "severity": "high",
        "steps": [72, 73],
        "evidence": {"tool": "pytest", "error": "ModuleNotFoundError", "count": 2},
    },
    {
        "type": "human_intervention",
        "severity": "medium",
        "steps": [101],
        "evidence": {"message": "Нет, backend находится в другой папке"},
    },
    {
        "type": "token_hotspot",
        "severity": "medium",
        "steps": [120, 140],
        "evidence": {"token_count": 24532},
    },
]


def example_issues() -> list[Issue]:
    """Fresh list of example issues."""
    return [Issue.model_validate(item) for item in EXAMPLE_ISSUE_DICTS]


EXAMPLE_ISSUES: list[Issue] = example_issues()
