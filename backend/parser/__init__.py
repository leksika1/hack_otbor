"""Facade over the root-level ``agent_log_parser`` module.

The parser lives at the repository root because it is developed in parallel by
another contributor. This package only re-exports it (plus a thin vendor
adapter) so the rest of the backend can ``from backend.parser import ...``
without caring where the file physically sits.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:  # normal case: the repository root is on sys.path
    from agent_log_parser import AgentLogParser, Finding, LogStep, SessionMetrics
except ImportError:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from agent_log_parser import AgentLogParser, Finding, LogStep, SessionMetrics

from .adapter import SessionParser

__all__ = [
    "AgentLogParser",
    "SessionParser",
    "LogStep",
    "Finding",
    "SessionMetrics",
]
