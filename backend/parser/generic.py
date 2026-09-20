"""Fallback adapter for logs that match neither Codex nor Claude Code.

It never fails: unknown records become typed steps with whatever could be
recognised, so an unfamiliar vendor format still produces a usable timeline.
"""

from __future__ import annotations

from typing import Any, Mapping

from .models import AGENT, UNKNOWN, USER, ParseWarning
from .utils import (
    as_mapping,
    content_text,
    decode_maybe_json,
    first_value,
    parse_timestamp,
    preview,
    to_float,
    to_int,
    to_str,
)

__all__ = ["GenericAdapter"]

_HUMAN_ROLES = {"user", "human", "user_message", "input", "interrupt", "approval", "feedback"}
_AGENT_ROLES = {"assistant", "agent", "model", "tool", "tool_call", "tool_result"}
_ERROR_STATES = {"error", "failed", "failure", "exception", "timeout"}
_SUCCESS_STATES = {"success", "ok", "completed", "done"}


class GenericAdapter:
    name = "generic"

    @staticmethod
    def matches(event: Mapping[str, Any]) -> bool:
        return True

    def normalize(
        self, event: Mapping[str, Any], line: int, warnings: list[ParseWarning]
    ) -> list[dict[str, Any]]:
        payload = as_mapping(event.get("payload")) or as_mapping(event.get("data")) or event
        usage = as_mapping(payload.get("usage")) or as_mapping(event.get("usage")) or {}
        event_type = (to_str(event, "type", "event_type", "kind", "role") or "unknown").lower()
        role = (to_str(event, "role", "actor", "author", "source") or event_type).lower()
        raw_status = str(first_value(payload, "status", "result", "outcome")
                         or first_value(event, "status", "result", "outcome") or "").lower()
        error = self._error(event) or self._error(payload)

        if raw_status in _ERROR_STATES or error:
            status = "error"
        elif raw_status in _SUCCESS_STATES:
            status = "success"
        elif "cancel" in raw_status:
            status = "cancelled"
        else:
            status = "unknown"

        if role in _HUMAN_ROLES or "user" in role or "human" in role:
            actor = USER
        elif role in _AGENT_ROLES:
            actor = AGENT
        else:
            actor = UNKNOWN

        tool = to_str(payload, "tool_name", "tool", "name", "command_name") or to_str(event, "tool_name", "tool")
        return [{
            "line": line,
            "timestamp": parse_timestamp(first_value(event, "timestamp", "time", "created_at", "createdAt", "ts")),
            "event_type": event_type,
            "actor": actor,
            "tool_name": tool,
            "tool_arguments": decode_maybe_json(
                first_value(payload, "tool_input", "arguments", "input", "params", "parameters")
            ),
            "status": status,
            "text": content_text(first_value(payload, "text", "content", "message", "summary")),
            "error": error or None,
            "input_tokens": to_int(first_value(usage, "input_tokens", "prompt_tokens")
                                   or event.get("input_tokens")),
            "output_tokens": to_int(first_value(usage, "output_tokens", "completion_tokens")
                                    or event.get("output_tokens")),
            "cost": to_float(first_value(usage, "cost", "cost_usd") or first_value(event, "cost", "cost_usd")),
            "raw_preview": preview(event),
        }]

    @staticmethod
    def _error(scope: Mapping[str, Any]) -> str:
        for key in ("error", "stderr", "exception", "failure_reason"):
            value = scope.get(key)
            if value:
                return str(value)[:1000]
        return ""
