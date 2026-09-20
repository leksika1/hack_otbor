"""Claude Code JSONL adapter.

Records look like::

    {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", ...}],
                                      "usage": {...}}}
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", ...}]}}

Three properties of this format drive the implementation:

* the same message can be written several times while it streams, so blocks are
  de-duplicated by ``tool_use.id`` / ``tool_result.tool_use_id`` / ``uuid``;
* ``message.usage`` is cumulative per ``message.id``, so tokens are counted as a
  delta and skipped (with a warning) when there is no id to group by;
* a ``tool_result`` is written with role ``user`` but is not a human message.
"""

from __future__ import annotations

from typing import Any, Mapping

from .models import AGENT, USER, ParseWarning
from .utils import as_mapping, content_text, parse_timestamp, preview, to_int

__all__ = ["ClaudeAdapter"]

# Claude reports these input categories separately; the nested cache_creation
# breakdown repeats them and must not be added twice.
_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
_OUTPUT_FIELDS = ("output_tokens",)


class ClaudeAdapter:
    """Stateful per session: de-duplication and cumulative token accounting."""

    name = "claude"

    def __init__(self) -> None:
        self._seen_blocks: set[str] = set()
        self._call_names: dict[str, str] = {}
        self._seen_users: set[str] = set()
        self._usage: dict[str, dict[str, int]] = {}

    @staticmethod
    def matches(event: Mapping[str, Any]) -> bool:
        return str(event.get("type", "")) in {"assistant", "user"} and isinstance(
            event.get("message"), Mapping
        )

    def normalize(
        self, event: Mapping[str, Any], line: int, warnings: list[ParseWarning]
    ) -> list[dict[str, Any]]:
        message = as_mapping(event.get("message")) or {}
        role = str(event.get("type", ""))
        common = {
            "line": line,
            "timestamp": parse_timestamp(event.get("timestamp")),
            "raw_preview": preview(event),
        }
        blocks = message.get("content") if isinstance(message.get("content"), list) else []
        steps: list[dict[str, Any]] = []

        for position, block in enumerate(blocks):
            if not isinstance(block, Mapping):
                continue
            block_type = str(block.get("type", ""))

            if role == "assistant" and block_type == "tool_use":
                key = block.get("id")
                if isinstance(key, str) and not self._mark(f"call:{key}"):
                    continue
                tool_name = str(block.get("name")) if block.get("name") else None
                if isinstance(key, str) and tool_name:
                    self._call_names[key] = tool_name
                steps.append({
                    **common,
                    "event_type": "tool_call",
                    "actor": AGENT,
                    "tool_name": tool_name,
                    "tool_arguments": block.get("input"),
                    "call_id": key if isinstance(key, str) else None,
                })

            elif role == "assistant" and block_type == "text":
                key = f"text:{message.get('id')}:{position}"
                if message.get("id") and not self._mark(key):
                    continue
                text = str(block.get("text") or "").strip()
                if text:
                    steps.append({**common, "event_type": "message", "actor": AGENT, "text": text[:4000]})

            elif role == "user" and block_type == "tool_result":
                key = block.get("tool_use_id")
                if isinstance(key, str) and not self._mark(f"result:{key}"):
                    continue
                is_error = block.get("is_error")
                status = "error" if is_error is True else ("success" if is_error in (False, None) else "unknown")
                text = content_text(block.get("content")) or str(block.get("content") or "")[:2000]
                steps.append({
                    **common,
                    "event_type": "tool_result",
                    "actor": AGENT,
                    "tool_name": self._call_names.get(key) if isinstance(key, str) else None,
                    "call_id": key if isinstance(key, str) else None,
                    "status": status,
                    "error": text[:1000] if status == "error" else None,
                    "text": text or None,
                })

        if role == "user" and self._is_human_turn(event, message, blocks):
            key = event.get("uuid") or message.get("id")
            if not isinstance(key, str) or self._mark(f"user:{key}"):
                steps.append({
                    **common,
                    "event_type": "user_message",
                    "actor": USER,
                    "text": content_text(message.get("content")),
                })

        if role == "assistant" and isinstance(message.get("usage"), Mapping):
            usage = self._usage_delta(message, warnings, line)
            if usage:
                if steps:
                    steps[0].update(usage)
                else:
                    steps.append({**common, "event_type": "token_count", "actor": AGENT,
                                  "status": "success", **usage})
        return steps

    # ------------------------------------------------------------------ #

    def _mark(self, key: str) -> bool:
        """Return True the first time a key is seen (i.e. "not a duplicate")."""
        if key in self._seen_blocks:
            return False
        self._seen_blocks.add(key)
        return True

    @staticmethod
    def _is_human_turn(event: Mapping[str, Any], message: Mapping[str, Any], blocks: list) -> bool:
        if event.get("isMeta") is True or event.get("isSynthetic") is True:
            return False
        if any(isinstance(block, Mapping) and block.get("type") == "tool_result" for block in blocks):
            return False
        content = message.get("content")
        if isinstance(content, str):
            return bool(content.strip())
        return any(
            isinstance(block, Mapping) and block.get("type") == "text" and str(block.get("text") or "").strip()
            for block in blocks
        )

    def _usage_delta(
        self, message: Mapping[str, Any], warnings: list[ParseWarning], line: int
    ) -> dict[str, int] | None:
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id:
            warnings.append(ParseWarning(
                "CLAUDE_USAGE_WITHOUT_MESSAGE_ID",
                "token usage skipped: duplicates cannot be removed without message.id",
                line,
            ))
            return None

        usage = as_mapping(message.get("usage")) or {}
        previous = self._usage.get(message_id, {})
        current = dict(previous)
        delta_in = delta_out = 0
        valid = False
        for field in _USAGE_FIELDS:
            raw = usage.get(field)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                continue
            valid = True
            if raw < previous.get(field, 0):
                warnings.append(ParseWarning(
                    "CLAUDE_USAGE_DECREASED",
                    f"counter {field} decreased for {message_id}; keeping the maximum",
                    line,
                ))
            current[field] = max(raw, previous.get(field, 0))
            delta = current[field] - previous.get(field, 0)
            if field in _OUTPUT_FIELDS:
                delta_out += delta
            else:
                delta_in += delta
        if not valid:
            return None
        self._usage[message_id] = current
        if not (delta_in or delta_out):
            return None
        return {"input_tokens": to_int(delta_in), "output_tokens": to_int(delta_out)}
