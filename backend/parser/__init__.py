"""Log parsing: raw JSONL -> normalized ``Step`` objects.

Supported formats: Codex desktop rollout, Claude Code, and a tolerant generic
fallback. ``SessionParser(log_format="auto")`` picks one by inspecting the log.
"""

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .generic import GenericAdapter
from .models import AGENT, SYSTEM, UNKNOWN, USER, ParseResult, ParseWarning, Step
from .parser import LOG_FORMATS, SessionParser, detect_format, parse_bytes, parse_lines

__all__ = [
    "Step",
    "ParseResult",
    "ParseWarning",
    "SessionParser",
    "parse_lines",
    "parse_bytes",
    "detect_format",
    "LOG_FORMATS",
    "CodexAdapter",
    "ClaudeAdapter",
    "GenericAdapter",
    "AGENT",
    "USER",
    "SYSTEM",
    "UNKNOWN",
]
