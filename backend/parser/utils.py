"""Small, defensive helpers shared by the format adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

__all__ = [
    "as_mapping", "first_value", "to_str", "to_int", "to_float",
    "parse_timestamp", "decode_maybe_json", "content_text", "canonical",
    "preview", "result_status",
]

MAX_PREVIEW = 500
MAX_TEXT = 4000


def as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def first_value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def to_str(data: Mapping[str, Any], *keys: str) -> str | None:
    value = first_value(data, *keys)
    return str(value) if isinstance(value, (str, int, float)) else None


def to_int(value: Any) -> int:
    try:
        if isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def to_float(value: Any) -> float:
    try:
        if isinstance(value, bool):
            return 0.0
        return max(0.0, float(value))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def parse_timestamp(value: Any) -> datetime | None:
    """ISO-8601 or epoch seconds/milliseconds. Returns ``None`` when unusable."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            divisor = 1000 if value > 10_000_000_000 else 1
            return datetime.fromtimestamp(float(value) / divisor, timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def decode_maybe_json(value: Any) -> Any:
    """Tool arguments are often a JSON string; decode when possible."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def content_text(value: Any) -> str | None:
    """Flatten Anthropic/OpenAI style ``content`` into plain text."""
    if isinstance(value, str):
        return value[:MAX_TEXT] or None
    if isinstance(value, list):
        parts = [
            str(block.get("text", ""))
            for block in value
            if isinstance(block, Mapping) and block.get("type") in (None, "text", "output_text")
        ]
        joined = "\n".join(part for part in parts if part)
        return joined[:MAX_TEXT] or None
    return None


def canonical(value: Any) -> str:
    """Stable string form of tool arguments, used for similarity comparison."""
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))[:20000]
    except (TypeError, ValueError):
        return repr(value)[:20000]


def preview(event: Any) -> str:
    try:
        text = json.dumps(event, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(event)
    return text[:MAX_PREVIEW]


def result_status(output: Any) -> tuple[str, str]:
    """Classify a tool result. Returns ``(status, error_text)``.

    Deliberately conservative: the word "error" inside arbitrary tool output is
    not evidence of a failure (it appears in source files and test names), so
    only explicit markers are trusted.
    """
    value = decode_maybe_json(output)
    text = ""
    if isinstance(value, Mapping):
        text = str(first_value(value, "output", "stdout", "content", "result") or "")
        metadata = as_mapping(value.get("metadata")) or {}
        if value.get("is_error") is True or value.get("isError") is True or value.get("success") is False:
            return "error", (str(first_value(value, "error", "stderr") or text) or "tool reported an error")[:1000]
        explicit = str(first_value(value, "error", "stderr") or "")
        if explicit.strip():
            return "error", explicit[:1000]
        for source in (metadata, value):
            code = source.get("exit_code")
            if code is not None:
                try:
                    code_int = int(code)
                except (TypeError, ValueError):
                    continue
                if code_int != 0:
                    last = text.strip().splitlines()[-1] if text.strip() else ""
                    return "error", f"exit_code={code_int} {last}".strip()[:1000]
                return "success", ""
        if value.get("is_error") is False or value.get("isError") is False or value.get("success") is True:
            return "success", ""
        return "unknown", ""

    if isinstance(output, str):
        for marker in ("Process exited with code", "Exit code:"):
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith(marker):
                    tail = stripped[len(marker):].strip().rstrip(".")
                    try:
                        return ("success", "") if int(tail) == 0 else ("error", stripped[:1000])
                    except ValueError:
                        break
    return "unknown", ""
