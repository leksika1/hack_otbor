"""The parser must never crash, whatever it is fed."""

from __future__ import annotations

import json

from backend.parser import SessionParser, detect_format, parse_bytes


def test_malformed_lines_become_warnings():
    result = SessionParser("generic").parse_lines(['{"type":"ok"}', "{not json", "", "   ", "[1,2]"])
    assert result.invalid_lines == 2
    assert len(result.steps) == 1
    assert {w.code for w in result.warnings} == {"INVALID_JSON", "NOT_AN_OBJECT"}


def test_unknown_events_do_not_crash():
    result = SessionParser("generic").parse_lines([json.dumps({"type": "totally_unknown", "payload": {"x": [1, 2]}})])
    assert result.steps[0].event_type == "totally_unknown"


def test_empty_input():
    result = parse_bytes(b"")
    assert result.steps == [] and result.is_empty


def test_bom_and_crlf_are_tolerated():
    payload = "﻿" + json.dumps({"type": "user", "content": "hi"}) + "\r\n"
    result = parse_bytes(payload, "generic")
    assert len(result.steps) == 1


def test_non_jsonl_text_produces_no_steps():
    result = parse_bytes(b"hello world\nthis is a text file\n")
    assert result.steps == []
    assert result.invalid_lines == 2


def test_format_detection():
    codex = [{"type": "response_item", "payload": {"type": "function_call", "name": "x"}}]
    claude = [{"type": "assistant", "message": {"id": "m", "content": []}}]
    assert detect_format(codex) == "codex"
    assert detect_format(claude) == "claude"
    assert detect_format([{"type": "something"}]) == "generic"


def test_step_ids_are_unique_and_sequential():
    rows = [{"type": "assistant", "message": {"id": f"m{i}", "content": [
        {"type": "tool_use", "id": f"t{i}", "name": "Read", "input": {}}]}} for i in range(5)]
    result = SessionParser("claude").parse_lines(json.dumps(row) for row in rows)
    assert [step.id for step in result.steps] == list(range(len(result.steps)))
    assert len({step.id for step in result.steps}) == len(result.steps)


def test_line_numbers_survive_broken_lines():
    result = SessionParser("generic").parse_lines(["{bad", json.dumps({"type": "user", "content": "hi"})])
    assert result.steps[0].line == 2
