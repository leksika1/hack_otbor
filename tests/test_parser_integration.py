"""Parser / analyzer behaviour the pipeline depends on."""

from __future__ import annotations

import json
from pathlib import Path

from backend.parser import SessionParser

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def parse(rows):
    parser = SessionParser(bucket_size=5)
    steps = parser.parse_lines(json.dumps(row) for row in rows)
    return parser, steps, parser.analyze(steps)


def test_malformed_jsonl_does_not_crash():
    parser = SessionParser()
    steps = parser.parse_lines(['{"type":"ok"}', "{not json", "", "   ", '{"type":'])
    metrics = parser.analyze(steps)
    assert len(steps) == 3  # blank lines skipped, broken lines kept as evidence
    assert metrics.parse_warnings


def test_unknown_event_does_not_crash():
    parser, steps, metrics = parse([{"type": "totally_unknown", "payload": {"weird": [1, 2]}}])
    assert steps[0].event_type == "totally_unknown"
    assert metrics.total_steps == 1


def test_initial_user_message_is_not_an_intervention():
    _, _, metrics = parse([
        {"type": "user", "content": "implement the API"},
        {"type": "assistant", "content": "working"},
    ])
    assert metrics.human_interventions == []


def test_correction_after_agent_work_is_an_intervention():
    _, _, metrics = parse([
        {"type": "user", "content": "implement the API"},
        {"type": "assistant", "content": "working"},
        {"type": "user", "content": "no, backend is in another directory"},
    ])
    assert len(metrics.human_interventions) == 1
    finding = metrics.human_interventions[0]
    assert finding.step_indices == (2,)
    assert finding.evidence["message"] == "no, backend is in another directory"


def test_token_hotspot_is_detected():
    rows = [{"type": "assistant", "usage": {"input_tokens": 10}} for _ in range(20)]
    rows[7]["usage"] = {"input_tokens": 5000}
    _, _, metrics = parse(rows)
    assert metrics.token_hotspots
    hotspot = metrics.token_hotspots[0]
    assert hotspot.kind == "token_hotspot"
    assert hotspot.evidence["token_count"] >= 5000


def test_no_token_data_produces_no_hotspots():
    rows = [{"type": "assistant", "content": "x"} for _ in range(20)]
    _, _, metrics = parse(rows)
    assert metrics.token_hotspots == []


def test_codex_tool_output_error_is_detected():
    rows = [
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                              "call_id": "c1", "arguments": '{"command":["pytest"]}'}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                              "output": json.dumps({"output": "ModuleNotFoundError",
                                                                    "metadata": {"exit_code": 1}})}},
    ]
    _, steps, metrics = parse(rows)
    assert steps[1].event_type == "function_call_output"
    assert steps[1].tool_name == "shell"  # linked back to the call
    assert steps[1].status == "error"
    assert any(f.kind in {"tool_error", "tool_retry"} for f in metrics.errors)


def test_codex_token_count_events_are_counted():
    rows = [{"type": "event_msg", "payload": {"type": "token_count",
                                              "info": {"last_token_usage": {"input_tokens": 120,
                                                                            "output_tokens": 30}}}}]
    _, steps, metrics = parse(rows)
    assert steps[0].tokens == 150
    assert metrics.total_tokens == 150


def test_fixture_log_is_analyzable():
    parser = SessionParser(bucket_size=5)
    steps = parser.parse_file(FIXTURE)
    metrics = parser.analyze(steps)
    kinds = {finding.kind for finding in metrics.findings}
    assert steps and metrics.parse_warnings          # the fixture contains broken lines on purpose
    assert {"loop", "human_intervention"} <= kinds
