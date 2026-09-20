"""HTTP layer. Skipped automatically when FastAPI is not installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="FastAPI is not installed in this environment")

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import create_app  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "codex_session.jsonl"
client = TestClient(create_app())


def upload(path=FIXTURE, url="/api/analyze", name="session.jsonl"):
    with Path(path).open("rb") as handle:
        return client.post(url, files={"file": (name, handle, "application/json")})


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {"llm_configured", "provider", "model", "version"} <= set(body)


def test_health_is_also_served_under_api():
    assert client.get("/api/health").status_code == 200


def test_analyze_returns_the_full_report():
    response = upload()
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["steps"] > 0
    assert body["summary"]["log_format"] == "codex"
    assert body["summary"]["file_name"] == "session.jsonl"
    assert body["findings"] and body["explanations"] and body["steps"]
    assert body["agents_md"].startswith("# Agent Rules")
    assert body["provider"] and body["provider_is_mock"] is True
    explanation = body["explanations"][0]
    assert {"issue_type", "severity", "steps", "title", "explanation",
            "impact", "recommendation", "agent_rule"} <= set(explanation)


def test_legacy_alias_still_works():
    assert upload(url="/analyze").status_code == 200


def test_claude_log_is_detected():
    response = upload(FIXTURE.parent / "claude_session.jsonl")
    assert response.json()["summary"]["log_format"] == "claude"


def test_empty_upload_is_rejected():
    response = client.post("/api/analyze", files={"file": ("empty.jsonl", b"", "application/json")})
    assert response.status_code == 400


def test_non_jsonl_upload_is_rejected():
    response = client.post("/api/analyze", files={"file": ("notes.txt", b"hello\nworld\n", "text/plain")})
    assert response.status_code == 422


def test_too_large_upload_is_rejected(monkeypatch):
    from backend.core import config

    small = config.Settings(max_upload_bytes=1024)
    app = create_app(small)
    app.dependency_overrides[config.get_settings] = lambda: small
    with TestClient(app) as local:
        payload = (json.dumps({"type": "user", "content": "x" * 50}) + "\n").encode() * 100
        response = local.post("/api/analyze", files={"file": ("big.jsonl", payload, "application/json")})
    assert response.status_code == 413


def test_broken_lines_are_tolerated():
    payload = b"\n".join([
        json.dumps({"type": "user", "content": "go"}).encode(),
        b"{ broken",
        json.dumps({"type": "assistant", "content": "ok"}).encode(),
    ])
    response = client.post("/api/analyze", files={"file": ("mixed.jsonl", payload, "application/json")})
    assert response.status_code == 200
    assert response.json()["summary"]["invalid_lines"] == 1


def test_deterministic_only_mode():
    with FIXTURE.open("rb") as handle:
        response = client.post("/api/analyze?explain=false",
                               files={"file": ("session.jsonl", handle, "application/json")})
    body = response.json()
    assert response.status_code == 200
    assert body["explanations"] == [] and body["findings"]


def test_invalid_log_format_is_rejected():
    with FIXTURE.open("rb") as handle:
        response = client.post("/api/analyze?log_format=nope",
                               files={"file": ("session.jsonl", handle, "application/json")})
    assert response.status_code == 400


def test_agents_md_endpoint_deduplicates():
    explanation = {
        "issue_type": "repeated_tool_call", "severity": "high", "steps": [1, 2],
        "title": "t", "explanation": "e", "impact": "i", "recommendation": "r",
        "agent_rule": "Do not repeat an identical repository search.",
    }
    response = client.post("/api/agents-md", json={"explanations": [explanation, explanation]})
    assert response.status_code == 200
    assert response.json()["agents_md"].count("Do not repeat an identical repository search.") == 1


def test_openapi_is_available():
    assert client.get("/openapi.json").status_code == 200
