"""Claude Code format: de-duplication, usage accounting, tool results."""

from __future__ import annotations

import json
from pathlib import Path

from backend.parser import SessionParser

FIXTURE = Path(__file__).parent / "fixtures" / "claude_session.jsonl"


def parse(rows, log_format="claude"):
    return SessionParser(log_format).parse_lines(json.dumps(row) for row in rows)


def test_tool_use_block_becomes_a_step():
    result = parse([{"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "a", "name": "Read", "input": {"file_path": "a.js"}}]}}])
    step = result.steps[0]
    assert step.event_type == "tool_call"
    assert step.tool_name == "Read"
    assert step.tool_arguments == {"file_path": "a.js"}


def test_repeated_streaming_line_is_not_counted_twice():
    row = {"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "a", "name": "Read", "input": {"file_path": "a.js"}},
        {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "b.js"}}]}}
    result = parse([row, row])
    assert len([s for s in result.steps if s.event_type == "tool_call"]) == 2


def test_usage_is_counted_as_a_delta_per_message_id():
    usage = {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50,
             "cache_creation_input_tokens": 10}
    first = {"type": "assistant", "message": {"id": "m1", "content": [], "usage": dict(usage)}}
    grown = {"type": "assistant", "message": {"id": "m1", "content": [], "usage": {**usage, "output_tokens": 30}}}
    other = {"type": "assistant", "message": {"id": "m2", "content": [], "usage": {**usage, "output_tokens": 30}}}
    result = parse([first, first, grown, other])
    # 180 for m1, +10 when its output grows, 190 for m2 - duplicates add nothing.
    assert sum(step.tokens for step in result.steps) == 380


def test_usage_without_message_id_is_skipped_with_a_warning():
    result = parse([{"type": "assistant", "message": {"content": [], "usage": {"input_tokens": 100}}}])
    assert sum(step.tokens for step in result.steps) == 0
    assert any(w.code == "CLAUDE_USAGE_WITHOUT_MESSAGE_ID" for w in result.warnings)


def test_tool_result_is_not_a_human_message():
    result = parse([{"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "a", "is_error": True, "content": "boom"}]}}])
    assert [step.event_type for step in result.steps] == ["tool_result"]
    assert result.steps[0].actor == "agent"
    assert result.steps[0].status == "error"


def test_meta_and_synthetic_turns_are_ignored():
    result = parse([{"type": "user", "isMeta": True, "uuid": "x",
                     "message": {"role": "user", "content": "system reminder"}}])
    assert result.steps == []


def test_unknown_blocks_are_safe():
    result = parse([{"type": "assistant", "message": {"id": "m1", "content": [None, {"type": "future"}]}}])
    assert result.steps == []
    assert not result.warnings


def test_fixture_is_detected_and_parsed():
    result = SessionParser().parse_file(FIXTURE)
    assert result.log_format == "claude"
    assert result.invalid_lines == 1
    tools = [step.tool_name for step in result.steps if step.event_type == "tool_call"]
    assert tools == ["Bash", "Bash", "Edit", "Bash"]
    assert sum(step.tokens for step in result.steps) == 25035
