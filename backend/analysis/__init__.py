"""Glue between the deterministic parser/analyzer and the LLM layer."""

from .adapters import FINDING_TYPE_MAP, finding_to_issue, findings_to_issues
from .context import build_issue_context, enrich_issues_with_context

__all__ = [
    "FINDING_TYPE_MAP",
    "finding_to_issue",
    "findings_to_issues",
    "build_issue_context",
    "enrich_issues_with_context",
]
