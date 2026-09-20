"""Session parser: raw JSONL lines -> normalized ``Step`` list.

The parser owns three things and nothing else: reading lines, choosing a format
adapter, and assigning step ids. All analysis lives in ``backend.analysis``.
It never raises on bad input - malformed lines become warnings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .generic import GenericAdapter
from .models import ParseResult, ParseWarning, Step

__all__ = ["SessionParser", "parse_lines", "parse_bytes", "detect_format", "LOG_FORMATS"]

logger = logging.getLogger(__name__)

LOG_FORMATS = ("auto", "codex", "claude", "generic")
_DETECTION_SAMPLE = 200


def detect_format(events: Iterable[Mapping[str, Any]]) -> str:
    """Pick an adapter by looking at a sample of decoded events."""
    codex = claude = 0
    for index, event in enumerate(events):
        if index >= _DETECTION_SAMPLE:
            break
        if CodexAdapter.matches(event):
            codex += 1
        elif ClaudeAdapter.matches(event):
            claude += 1
    if not codex and not claude:
        return "generic"
    return "codex" if codex >= claude else "claude"


class SessionParser:
    """Turns a JSONL session log into ``Step`` objects."""

    def __init__(self, log_format: str = "auto") -> None:
        if log_format not in LOG_FORMATS:
            raise ValueError(f"log_format must be one of {LOG_FORMATS}")
        self.log_format = log_format

    # -- entry points --------------------------------------------------- #

    def parse_lines(self, lines: Iterable[str | bytes]) -> ParseResult:
        decoded, result = self._decode(lines)
        chosen = self.log_format if self.log_format != "auto" else detect_format(
            event for _, event in decoded
        )
        result.log_format = chosen
        adapter = {"codex": CodexAdapter, "claude": ClaudeAdapter, "generic": GenericAdapter}[chosen]()

        next_id = 0
        for line_number, event in decoded:
            try:
                produced = adapter.normalize(event, line_number, result.warnings)
            except Exception as exc:  # noqa: BLE001 - an adapter bug must not kill a run
                logger.warning("normalization failed on line %s: %s", line_number, exc)
                result.warnings.append(ParseWarning("NORMALIZATION_FAILED", type(exc).__name__, line_number))
                produced = []
            if not produced:
                result.ignored_lines += 1
                continue
            for payload in produced:
                result.steps.append(Step(id=next_id, **payload))
                next_id += 1

        logger.info(
            "parsed %s steps from %s lines (format=%s, invalid=%s, ignored=%s)",
            len(result.steps), result.total_lines, chosen, result.invalid_lines, result.ignored_lines,
        )
        return result

    def parse_bytes(self, data: bytes | str) -> ParseResult:
        text = data.decode("utf-8", "replace") if isinstance(data, (bytes, bytearray)) else str(data)
        return self.parse_lines(text.splitlines())

    def parse_file(self, path: str | Path) -> ParseResult:
        try:
            with Path(path).open(encoding="utf-8", errors="replace") as handle:
                return self.parse_lines(handle)
        except OSError as exc:
            result = ParseResult(log_format=self.log_format)
            result.warnings.append(ParseWarning("UNREADABLE_FILE", f"{type(exc).__name__}: {exc}"))
            return result

    # -- internals ------------------------------------------------------ #

    @staticmethod
    def _decode(lines: Iterable[str | bytes]) -> tuple[list[tuple[int, Mapping[str, Any]]], ParseResult]:
        result = ParseResult()
        decoded: list[tuple[int, Mapping[str, Any]]] = []
        for number, raw in enumerate(lines, start=1):
            result.total_lines = number
            try:
                text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
            except Exception:  # noqa: BLE001 - hostile iterables
                result.invalid_lines += 1
                result.warnings.append(ParseWarning("UNREADABLE_LINE", line=number))
                continue
            if number == 1:
                text = text.lstrip("﻿")
            if not text.strip():
                continue
            try:
                event = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                result.invalid_lines += 1
                result.warnings.append(ParseWarning("INVALID_JSON", line=number))
                continue
            if not isinstance(event, Mapping):
                result.invalid_lines += 1
                result.warnings.append(ParseWarning("NOT_AN_OBJECT", line=number))
                continue
            decoded.append((number, event))
        return decoded, result


def parse_lines(lines: Iterable[str | bytes], log_format: str = "auto") -> ParseResult:
    return SessionParser(log_format).parse_lines(lines)


def parse_bytes(data: bytes | str, log_format: str = "auto") -> ParseResult:
    return SessionParser(log_format).parse_bytes(data)
