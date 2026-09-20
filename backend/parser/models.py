"""Normalized parser output - the single internal contract for a session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["Step", "ParseWarning", "ParseResult", "AGENT", "USER", "SYSTEM", "UNKNOWN"]

AGENT = "agent"
USER = "user"
SYSTEM = "system"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Step:
    """One normalized event of a coding-agent session.

    ``id`` is assigned by the parser and is what every finding refers to.
    ``line`` keeps the physical JSONL line so a step can be traced back to the
    original file even when one line produces several steps.
    """

    id: int
    line: int = 0
    event_type: str = "unknown"
    timestamp: datetime | None = None
    actor: str = UNKNOWN
    tool_name: str | None = None
    tool_arguments: Any = None
    call_id: str | None = None
    status: str = "unknown"  # success | error | cancelled | unknown
    text: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    # Bounded preview instead of the whole raw event: keeps memory and API
    # payloads small and avoids echoing a full session log anywhere.
    raw_preview: str = ""

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def is_tool_call(self) -> bool:
        return bool(self.tool_name) and "output" not in self.event_type and "result" not in self.event_type

    @property
    def is_tool_result(self) -> bool:
        return "output" in self.event_type or "result" in self.event_type


@dataclass(frozen=True)
class ParseWarning:
    """Something the parser could not interpret. Never an exception."""

    code: str
    detail: str = ""
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line is not None else ""
        return f"{where}{self.code}{': ' + self.detail if self.detail else ''}"


@dataclass
class ParseResult:
    steps: list[Step] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    log_format: str = "unknown"
    total_lines: int = 0
    invalid_lines: int = 0
    ignored_lines: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.steps
