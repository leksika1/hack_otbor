"""API smoke tests. Skipped automatically when FastAPI is not installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="FastAPI is not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import app  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "provider" in body and "llm_configured" in body


def test_analyze_returns_findings_and_explanations():
    with FIXTURE.open("rb") as handle:
        response = client.post("/analyze", files={"file": ("session.jsonl", handle, "application/json")})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["steps"] > 0
    assert body["findings"]
    assert body["explanations"]
    assert body["provider"]
    assert body["agents_md"].startswith("# Agent Rules")
    first = body["explanations"][0]
    assert {"issue_type", "severity", "steps", "title", "explanation",
            "impact", "recommendation", "agent_rule"} <= set(first)


def test_analyze_rejects_empty_file():
    response = client.post("/analyze", files={"file": ("empty.jsonl", b"", "application/json")})
    assert response.status_code == 400


def test_analyze_rejects_non_jsonl():
    response = client.post("/analyze", files={"file": ("notes.txt", b"hello\nworld\n", "text/plain")})
    assert response.status_code == 422


def test_analyze_survives_broken_lines():
    payload = b"\n".join([
        json.dumps({"type": "user", "content": "go"}).encode(),
        b"{ broken",
        json.dumps({"type": "assistant", "content": "ok"}).encode(),
    ])
    response = client.post("/analyze", files={"file": ("mixed.jsonl", payload, "application/json")})
    assert response.status_code == 200
    assert response.json()["summary"]["invalid_lines"] == 1


def test_analyze_without_llm():
    with FIXTURE.open("rb") as handle:
        response = client.post("/analyze?explain=false",
                               files={"file": ("session.jsonl", handle, "application/json")})
    assert response.status_code == 200
    body = response.json()
    assert body["explanations"] == []
    assert body["findings"]


def test_dashboard_endpoint_matches_frontend_contract():
    with FIXTURE.open("rb") as handle:
        response = client.post("/api/analyze", files={"file": ("session.jsonl", handle, "application/json")})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["fileName"] == "session.jsonl"
    assert body["metrics"] and body["logSteps"]
    assert body["artifactText"].startswith("# Agent Rules")


def test_generate_agents_md_endpoint():
    explanation = {
        "issue_type": "repeated_tool_call", "severity": "high", "steps": [1, 2],
        "title": "t", "explanation": "e", "impact": "i", "recommendation": "r",
        "agent_rule": "Do not repeat an identical repository search.",
    }
    response = client.post("/generate-agents-md", json={"explanations": [explanation, explanation]})
    assert response.status_code == 200
    markdown = response.json()["agents_md"]
    assert markdown.count("Do not repeat an identical repository search.") == 1
