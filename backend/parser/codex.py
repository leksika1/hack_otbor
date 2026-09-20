"""Codex desktop rollout JSONL adapter.

Records look like::

    {"timestamp": "...", "type": "response_item",
     "payload": {"type": "function_call", "name": "shell", "call_id": "c1", ...}}
    {"timestamp": "...", "type": "event_msg",
     "payload": {"type": "token_count", "info": {...}}}
"""

from __future__ import annotations

from typing import Any, Mapping

from .models import AGENT, USER, ParseWarning
from .utils import (
    as_mapping,
    content_text,
    decode_maybe_json,
    first_value,
    parse_timestamp,
    preview,
    result_status,
    to_int,
    to_str,
)

__all__ = ["CodexAdapter"]

_TOOL_CALL_TYPES = {"function_call", "custom_tool_call", "local_shell_call"}
_TOOL_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}
_USER_ITEM_TYPES = {"usermessage", "user_message"}


class CodexAdapter:
    """Stateful per session: links tool outputs back to their call names."""

    name = "codex"

    def __init__(self) -> None:
        self._call_names: dict[str, str] = {}
        self._cumulative_tokens = 0

    @staticmethod
    def matches(event: Mapping[str, Any]) -> bool:
        return str(event.get("type", "")) in {"event_msg", "response_item"} and isinstance(
            event.get("payload"), Mapping
        )

    def normalize(
        self, event: Mapping[str, Any], line: int, warnings: list[ParseWarning]
    ) -> list[dict[str, Any]]:
        payload = as_mapping(event.get("payload")) or {}
        event_type = str(event.get("type", ""))
        payload_type = str(payload.get("type", ""))
        common = {
            "line": line,
            "timestamp": parse_timestamp(event.get("timestamp")),
            "raw_preview": preview(event),
        }

        if event_type == "response_item":
            if payload_type in _TOOL_CALL_TYPES:
                call_id = to_str(payload, "call_id", "id")
                name = to_str(payload, "name") or to_str(payload, "command_name")
                if call_id and name:
                    self._call_names[call_id] = name
                return [{
                    **common,
                    "event_type": "tool_call",
                    "actor": AGENT,
                    "tool_name": name,
                    "tool_arguments": decode_maybe_json(first_value(payload, "arguments", "input", "action")),
                    "call_id": call_id,
                }]

            if payload_type in _TOOL_OUTPUT_TYPES:
                call_id = to_str(payload, "call_id", "id")
                status, error = result_status(payload.get("output"))
                body = decode_maybe_json(payload.get("output"))
                text = str(first_value(body, "output", "stdout", "content") or "")[:2000] if isinstance(body, Mapping) else str(body or "")[:2000]
                return [{
                    **common,
                    "event_type": "tool_result",
                    "actor": AGENT,
                    "tool_name": self._call_names.get(call_id or ""),
                    "call_id": call_id,
                    "status": status,
                    "error": error or None,
                    "text": text or None,
                }]

            if payload_type == "message":
                # A user `response_item` duplicates the `event_msg` user message and
                # also carries harness-injected context, so only agent messages are kept.
                if str(payload.get("role", "")).lower() == "user":
                    return []
                return [{
                    **common,
                    "event_type": "message",
                    "actor": AGENT,
                    "text": content_text(payload.get("content")),
                }]
            return []

        if event_type == "event_msg":
            if payload_type == "user_message":
                return [{
                    **common,
                    "event_type": "user_message",
                    "actor": USER,
                    "text": content_text(first_value(payload, "message", "content", "text")),
                }]

            if payload_type == "item_completed":
                item = as_mapping(payload.get("item")) or {}
                item_type = str(item.get("type", "item_completed"))
                is_user = item_type.lower() in _USER_ITEM_TYPES
                return [{
                    **common,
                    "event_type": "user_message" if is_user else item_type.lower(),
                    "actor": USER if is_user else AGENT,
                    "text": content_text(item.get("content")),
                }]

            if payload_type == "agent_message":
                return [{
                    **common,
                    "event_type": "message",
                    "actor": AGENT,
                    "text": content_text(first_value(payload, "message", "content", "text")),
                }]

            if payload_type == "token_count":
                usage = self._token_usage(payload, warnings, line)
                if usage:
                    return [{**common, "event_type": "token_count", "actor": AGENT,
                             "status": "success", **usage}]
                return []

            if payload_type == "task_complete":
                error = as_mapping(payload.get("error"))
                return [{
                    **common,
                    "event_type": "task_complete",
                    "actor": AGENT,
                    "status": "error" if error else "success",
                    "error": str(first_value(error, "message", "detail") or "task failed") if error else None,
                }]
            return []
        return []

    def _token_usage(
        self, payload: Mapping[str, Any], warnings: list[ParseWarning], line: int
    ) -> dict[str, int] | None:
        """Per-turn usage. ``total_token_usage`` is cumulative, so use a delta."""
        info = as_mapping(payload.get("info")) or payload
        last = as_mapping(info.get("last_token_usage"))
        if last:
            return {
                "input_tokens": to_int(first_value(last, "input_tokens", "prompt_tokens")),
                "output_tokens": to_int(first_value(last, "output_tokens", "completion_tokens")),
            }
        total = as_mapping(info.get("total_token_usage"))
        if total:
            value = to_int(first_value(total, "total_tokens", "input_tokens"))
            if value < self._cumulative_tokens:
                warnings.append(ParseWarning("TOKEN_COUNTER_DECREASED",
                                             "cumulative token counter went backwards", line))
                self._cumulative_tokens = max(self._cumulative_tokens, value)
                return None
            delta = value - self._cumulative_tokens
            self._cumulative_tokens = value
            return {"input_tokens": delta, "output_tokens": 0} if delta else None
        return None
