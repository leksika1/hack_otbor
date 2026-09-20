"""Vendor adapter on top of ``AgentLogParser``.

``AgentLogParser`` documents ``normalize_event`` as its extension point, so this
module subclasses it instead of editing the shared parser file. It adds the two
Codex rollout records the generic branch cannot interpret:

* ``function_call_output`` - the result of a tool call (exit code / error);
* ``token_count``          - per-turn token usage.

Everything else falls through to the base implementation unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from . import AgentLogParser, LogStep

__all__ = ["SessionParser"]

_MAX_OUTPUT_CHARS = 2000


class SessionParser(AgentLogParser):
    """Parser used by the backend pipeline. Tolerant to unknown events."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call_names: dict[str, str] = {}

    def normalize_event(self, event: Mapping[str, Any], index: int) -> LogStep:
        payload = self._map(event.get("payload")) or {}
        payload_type = str(payload.get("type", ""))

        if event.get("type") == "response_item" and payload_type in {"function_call", "custom_tool_call"}:
            call_id = self._string(payload, "call_id", "id")
            name = self._string(payload, "name")
            if call_id and name:
                self._call_names[call_id] = name
            return super().normalize_event(event, index)

        if event.get("type") == "response_item" and payload_type in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            return self._tool_output(event, payload, index)

        if event.get("type") == "event_msg" and payload_type == "token_count":
            usage = self._token_usage(payload)
            if usage:
                warnings: list[str] = []
                return LogStep(
                    index=index,
                    event_type="token_count",
                    timestamp=self._time(event.get("timestamp"), warnings),
                    status="success",
                    actor="agent",
                    input_tokens=self._int(usage.get("input_tokens")),
                    output_tokens=self._int(usage.get("output_tokens")),
                    raw=dict(event),
                    parse_warnings=tuple(warnings),
                )

        return super().normalize_event(event, index)

    # ------------------------------------------------------------------ #

    def _tool_output(self, event: Mapping[str, Any], payload: Mapping[str, Any], index: int) -> LogStep:
        warnings: list[str] = []
        call_id = self._string(payload, "call_id", "id") or ""
        body = self._decode_arguments(payload.get("output"))
        text, error, exit_code = self._read_output(body)
        raw = dict(event)
        if error:
            # The base ``_errors`` detector reads well-known error keys from
            # ``raw``; surfacing the tool error there keeps that logic reusable.
            raw["error"] = error
        return LogStep(
            index=index,
            event_type="function_call_output",
            timestamp=self._time(event.get("timestamp"), warnings),
            tool_name=self._call_names.get(call_id),
            tool_arguments={"call_id": call_id} if call_id else None,
            status="error" if error else "success",
            text=(text or None),
            actor="agent",
            raw=raw,
            parse_warnings=tuple(warnings),
        )

    @staticmethod
    def _read_output(body: Any) -> tuple[str, str, int | None]:
        """Return ``(text, error, exit_code)`` from a tool-output payload."""
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                return body[:_MAX_OUTPUT_CHARS], "", None
        if not isinstance(body, Mapping):
            return (str(body)[:_MAX_OUTPUT_CHARS] if body is not None else ""), "", None

        text = str(body.get("output") or body.get("stdout") or body.get("content") or "")[:_MAX_OUTPUT_CHARS]
        metadata = body.get("metadata") if isinstance(body.get("metadata"), Mapping) else {}
        exit_code: int | None = None
        for source in (metadata, body):
            value = source.get("exit_code")
            if value is not None:
                try:
                    exit_code = int(value)
                except (TypeError, ValueError):
                    exit_code = None
                break
        explicit = str(body.get("error") or body.get("stderr") or "")
        if explicit.strip():
            return text, explicit[:_MAX_OUTPUT_CHARS], exit_code
        if exit_code not in (None, 0):
            snippet = text.strip().splitlines()[-1] if text.strip() else ""
            return text, f"exit_code={exit_code} {snippet}".strip()[:_MAX_OUTPUT_CHARS], exit_code
        return text, "", exit_code

    @staticmethod
    def _token_usage(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        info = payload.get("info") if isinstance(payload.get("info"), Mapping) else payload
        if not isinstance(info, Mapping):
            return None
        for key in ("last_token_usage", "token_usage", "usage"):
            value = info.get(key)
            if isinstance(value, Mapping):
                return value
        if any(k in info for k in ("input_tokens", "output_tokens")):
            return info
        return None
