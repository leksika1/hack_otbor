"""End-to-end pipeline: JSONL -> findings -> issues -> LLM -> report."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.llm import Issue, LLMService, MockLLMProvider
from backend.pipeline import analyze_session, analyze_session_sync, select_top_issues

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def run(source, **kwargs):
    kwargs.setdefault("service", LLMService(MockLLMProvider()))
    return asyncio.run(analyze_session(source, **kwargs))


def test_full_pipeline_on_fixture():
    result = run(FIXTURE)
    assert result.summary.steps > 10
    assert result.summary.issues_total > 0
    assert result.findings and result.explanations
    assert result.provider == "mock" and result.provider_is_mock is True
    assert result.agents_md.startswith("# Agent Rules")
    # every explanation points back at concrete steps
    assert all(item.steps for item in result.explanations)


def test_findings_keep_deterministic_types_and_steps():
    result = run(FIXTURE)
    types = {finding.type for finding in result.findings}
    assert "repeated_tool_call" in types
    assert "human_intervention" in types
    for explanation in result.explanations:
        matching = [f for f in result.findings if f.type == explanation.issue_type]
        assert matching, explanation.issue_type
        assert explanation.severity in {f.severity for f in matching}


def test_broken_lines_do_not_break_the_run():
    payload = "\n".join([
        json.dumps({"type": "user", "content": "go"}),
        "{ broken",
        "plain text",
        json.dumps({"type": "assistant", "content": "ok"}),
    ])
    result = run(payload)
    assert result.summary.invalid_lines == 2
    assert result.summary.steps == 4


def test_empty_input_is_handled():
    result = run("")
    assert result.summary.steps == 0
    assert result.findings == [] and result.explanations == []
    assert result.warnings


def test_max_issues_limits_llm_calls():
    service = LLMService(MockLLMProvider())
    result = asyncio.run(analyze_session(FIXTURE, service=service, max_issues=2))
    assert len(result.explanations) <= 2
    assert result.summary.issues_total > len(result.explanations)


def test_explanations_can_be_disabled():
    result = run(FIXTURE, max_issues=0)
    assert result.explanations == []
    assert result.findings  # deterministic report still returned


def test_select_top_issues_collapses_duplicates():
    issues = [
        Issue(type="repeated_tool_call", severity="medium", steps=[i], evidence={"tool": "grep"})
        for i in range(5)
    ] + [Issue(type="idle_period", severity="low", steps=[9], evidence={})]
    selected = select_top_issues(issues, limit=5)
    assert len(selected) == 2
    top = [i for i in selected if i.type == "repeated_tool_call"][0]
    assert top.evidence.as_dict()["occurrences"] == 5


def test_select_top_issues_orders_by_severity():
    issues = [
        Issue(type="idle_period", severity="low", steps=[1]),
        Issue(type="tool_failure", severity="high", steps=[2]),
        Issue(type="token_hotspot", severity="medium", steps=[3]),
    ]
    assert [i.severity for i in select_top_issues(issues, 10)] == ["high", "medium", "low"]


def test_failing_provider_is_reported_not_hidden():
    class BrokenProvider:
        name = "openai-compatible"

        async def generate_issue_explanation(self, issue):
            raise RuntimeError("upstream 500")

    service = LLMService(BrokenProvider(), retries=0, fallback_to_mock=False)
    result = asyncio.run(analyze_session(FIXTURE, service=service))
    assert result.explanations == []
    assert result.findings
    assert any("explanation" in warning.lower() for warning in result.warnings)
    assert result.provider == "openai-compatible"


def test_mock_fallback_is_labelled_as_mock():
    class BrokenProvider:
        name = "openai-compatible"

        async def generate_issue_explanation(self, issue):
            raise RuntimeError("upstream 500")

    service = LLMService(BrokenProvider(), retries=0, fallback_to_mock=True)
    result = asyncio.run(analyze_session(FIXTURE, service=service))
    assert result.explanations
    assert result.provider == "mock-fallback"
    assert result.provider_is_mock is True
    assert any("mock" in warning.lower() for warning in result.warnings)


def test_sync_helper_works():
    result = analyze_session_sync(FIXTURE, service=LLMService(MockLLMProvider()))
    assert result.summary.steps > 0


def test_context_is_attached_but_log_is_not_dumped():
    """The LLM gets a small window, never the whole session."""
    captured = []

    class CapturingProvider:
        name = "capture"

        async def generate_issue_explanation(self, issue):
            captured.append(issue)
            return MockLLMProvider().build(issue)

    asyncio.run(analyze_session(FIXTURE, service=LLMService(CapturingProvider())))
    assert captured
    for issue in captured:
        assert issue.context
        assert len(issue.context) <= 3000
