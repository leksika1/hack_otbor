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

from .models import AGENT, SYSTEM, USER, ParseWarning
from .pricing import usage_cost
from .utils import as_mapping, content_text, parse_timestamp, preview, to_int

__all__ = ["ClaudeAdapter"]

# Claude reports these input categories separately; the nested cache_creation
# breakdown repeats them and must not be added twice.
# cache_read_input_tokens is deliberately left out: the cached prefix is re-read
# on every turn, so summing it turns a long session into billions of "tokens".
_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
_OUTPUT_FIELDS = ("output_tokens",)
# Billed (cheaply) but not counted as session tokens - see above.
_COST_ONLY_FIELDS = ("cache_read_input_tokens",)

# Records written with role "user" that no human typed: subagent prompts,
# compaction summaries and harness-injected command output.
_NON_HUMAN_FLAGS = ("isMeta", "isSynthetic", "isSidechain", "isCompactSummary", "isVisibleInTranscriptOnly")
# tool_result texts the harness writes when the human refuses or interrupts a call.
_USER_REJECTION_PREFIXES = (
    "the user doesn't want to proceed with this tool use",
    "the user doesn't want to take this action",
    "[request interrupted by user",
)
_INJECTED_PREFIXES = (
    "<local-command-stdout>", "<local-command-stderr>", "<command-name>", "<command-message>",
    "<command-args>", "<system-reminder>", "<task-notification>", "<bash-input>", "<bash-stdout>",
    "<bash-stderr>", "<user-prompt-submit-hook>", "caveat: the messages below",
)


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
        if str(event.get("type", "")) == "attachment":
            return isinstance(event.get("attachment"), Mapping)
        return str(event.get("type", "")) in {"assistant", "user"} and isinstance(
            event.get("message"), Mapping
        )

    def normalize(
        self, event: Mapping[str, Any], line: int, warnings: list[ParseWarning]
    ) -> list[dict[str, Any]]:
        message = as_mapping(event.get("message")) or {}
        role = str(event.get("type", ""))
        if role == "attachment":
            return self._queued_prompt(event, line)
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
                if status == "error" and text.lstrip().lower().startswith(_USER_REJECTION_PREFIXES):
                    status = "cancelled"
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
        elif role == "user" and not steps:
            # Harness-injected record (background-task notification, slash command,
            # compaction summary...). Not a human turn, but a real point in time:
            # it explains why the agent was waiting.
            text = (content_text(message.get("content")) or "").strip()
            if text:
                steps.append({**common, "event_type": self._system_event(event, text),
                              "actor": SYSTEM, "text": text[:500]})

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

    @staticmethod
    def _system_event(event: Mapping[str, Any], text: str) -> str:
        if text.lower().startswith("<task-notification>"):
            return "task_notification"
        if event.get("isCompactSummary") is True:
            return "compact_summary"
        return "system_event"

    def _queued_prompt(self, event: Mapping[str, Any], line: int) -> list[dict[str, Any]]:
        """``attachment/queued_command``: text typed while the agent was still working."""
        attachment = as_mapping(event.get("attachment")) or {}
        prompt = attachment.get("prompt")
        if attachment.get("type") != "queued_command" or not isinstance(prompt, str) or not prompt.strip():
            return []
        if prompt.lstrip().lower().startswith(_INJECTED_PREFIXES):
            return []  # the same notification also arrives as a "user" record
        return [{"line": line, "timestamp": parse_timestamp(event.get("timestamp")),
                 "raw_preview": preview(event), "event_type": "user_message",
                 "actor": USER, "text": prompt.strip()[:4000]}]

    def _mark(self, key: str) -> bool:
        """Return True the first time a key is seen (i.e. "not a duplicate")."""
        if key in self._seen_blocks:
            return False
        self._seen_blocks.add(key)
        return True

    @staticmethod
    def _is_human_turn(event: Mapping[str, Any], message: Mapping[str, Any], blocks: list) -> bool:
        if any(event.get(flag) is True for flag in _NON_HUMAN_FLAGS):
            return False
        if (content_text(message.get("content")) or "").lstrip().lower().startswith(_INJECTED_PREFIXES):
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
        deltas: dict[str, int] = {}
        valid = False
        for field in _USAGE_FIELDS + _COST_ONLY_FIELDS:
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
            delta = deltas[field] = current[field] - previous.get(field, 0)
            if field in _COST_ONLY_FIELDS:
                continue
            if field in _OUTPUT_FIELDS:
                delta_out += delta
            else:
                delta_in += delta
        if not valid:
            return None
        self._usage[message_id] = current
        cost = usage_cost(
            message.get("model") if isinstance(message.get("model"), str) else None,
            input_tokens=deltas.get("input_tokens", 0),
            output_tokens=deltas.get("output_tokens", 0),
            cache_write_tokens=deltas.get("cache_creation_input_tokens", 0),
            cache_read_tokens=deltas.get("cache_read_input_tokens", 0),
        )
        if not (delta_in or delta_out or cost):
            return None
        return {"input_tokens": to_int(delta_in), "output_tokens": to_int(delta_out), "cost": cost}
