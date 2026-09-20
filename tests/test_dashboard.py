"""View-model consumed by frontend/src/App.jsx."""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.dashboard import to_dashboard_payload
from backend.llm import LLMService, MockLLMProvider
from backend.pipeline import analyze_session, build_parser

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def analyze():
    parser = build_parser(20)
    result = asyncio.run(
        analyze_session(FIXTURE, service=LLMService(MockLLMProvider()), parser=parser)
    )
    return result, parser.steps


def test_payload_has_every_field_the_dashboard_reads():
    result, steps = analyze()
    payload = to_dashboard_payload(result, steps, filename="rollout.jsonl")

    summary = payload["summary"]
    assert summary["fileName"] == "rollout.jsonl"
    assert summary["duration"] != ""
    assert summary["totalTokens"] and summary["totalCost"].startswith("$")

    assert len(payload["metrics"]) == 4
    assert {"label", "value", "status"} <= set(payload["metrics"][0])

    assert payload["logSteps"]
    step = payload["logSteps"][0]
    assert {"id", "type", "tool", "action", "time", "cost", "width"} <= set(step)

    assert payload["artifactText"].startswith("# Agent Rules")


def test_canonical_fields_are_preserved():
    result, steps = analyze()
    payload = to_dashboard_payload(result, steps)
    assert payload["findings"] and payload["explanations"]
    assert payload["provider"] == "mock"
    assert payload["summary"]["steps"] == result.summary.steps


def test_step_types_are_dashboard_colours():
    result, steps = analyze()
    payload = to_dashboard_payload(result, steps)
    types = {step["type"] for step in payload["logSteps"]}
    assert types & {"error", "loop", "human", "success"}


def test_empty_session_does_not_break_the_payload():
    result = asyncio.run(analyze_session("", service=LLMService(MockLLMProvider())))
    payload = to_dashboard_payload(result, [], filename="empty.jsonl")
    assert payload["logSteps"] == []
    assert payload["summary"]["duration"] == "N/A"
    assert payload["metrics"][0]["value"] == "0"
