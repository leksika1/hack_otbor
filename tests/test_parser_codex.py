"""Codex rollout format."""

from __future__ import annotations

import json
from pathlib import Path

from backend.parser import SessionParser

FIXTURE = Path(__file__).parent / "fixtures" / "codex_session.jsonl"


def parse(rows, log_format="codex"):
    return SessionParser(log_format).parse_lines(json.dumps(row) for row in rows)


def test_tool_call_is_normalized():
    result = parse([{"type": "response_item", "timestamp": "2026-01-01T00:00:00Z",
                     "payload": {"type": "function_call", "name": "shell", "call_id": "c1",
                                 "arguments": '{"command": ["ls"]}'}}])
    step = result.steps[0]
    assert step.event_type == "tool_call"
    assert step.tool_name == "shell"
    assert step.tool_arguments == {"command": ["ls"]}
    assert step.timestamp is not None


def test_tool_output_carries_status_and_tool_name():
    result = parse([
        {"type": "response_item", "payload": {"type": "function_call", "name": "pytest", "call_id": "c1",
                                              "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                              "output": json.dumps({"output": "ModuleNotFoundError",
                                                                    "metadata": {"exit_code": 1}})}},
    ])
    output = result.steps[1]
    assert output.event_type == "tool_result"
    assert output.tool_name == "pytest"          # linked back to the call
    assert output.status == "error"
    assert "exit_code=1" in (output.error or "")


def test_successful_output_is_not_an_error():
    result = parse([
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "call_id": "c1",
                                              "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                              "output": json.dumps({"output": "error handling works",
                                                                    "metadata": {"exit_code": 0}})}},
    ])
    # The word "error" inside tool output must not be treated as a failure.
    assert result.steps[1].status == "success"


def test_user_message_comes_from_event_msg_only():
    result = parse([
        {"type": "event_msg", "payload": {"type": "user_message", "message": "do the thing"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "text", "text": "do the thing"}]}},
    ])
    # The response_item copy carries harness context and would double-count.
    assert [step.event_type for step in result.steps] == ["user_message"]
    assert result.steps[0].text == "do the thing"


def test_token_count_uses_per_turn_usage():
    result = parse([{"type": "event_msg", "payload": {"type": "token_count",
                                                      "info": {"last_token_usage": {"input_tokens": 120,
                                                                                    "output_tokens": 30}}}}])
    assert result.steps[0].tokens == 150


def test_cumulative_token_counter_is_converted_to_a_delta():
    result = parse([
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 500}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 900}}}},
    ])
    assert [step.tokens for step in result.steps] == [500, 400]


def test_task_complete_error():
    result = parse([{"type": "event_msg", "payload": {"type": "task_complete", "error": {"message": "limit"}}}])
    assert result.steps[0].status == "error"


def test_fixture_is_detected_and_parsed():
    result = SessionParser().parse_file(FIXTURE)
    assert result.log_format == "codex"
    assert len(result.steps) > 5
    assert result.invalid_lines == 2          # the fixture contains broken lines on purpose
    assert sum(step.tokens for step in result.steps) > 0
