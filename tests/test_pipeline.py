"""End-to-end pipeline: JSONL -> parser -> findings -> mock LLM -> report."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.llm import LLMService, MockLLMProvider
from backend.services import analyze_session, analyze_session_sync

FIXTURES = Path(__file__).parent / "fixtures"
CODEX = FIXTURES / "codex_session.jsonl"
CLAUDE = FIXTURES / "claude_session.jsonl"


def run(source, **kwargs):
    kwargs.setdefault("service", LLMService(MockLLMProvider()))
    return asyncio.run(analyze_session(source, **kwargs))


def test_codex_session_end_to_end():
    report = run(CODEX, file_name="codex_session.jsonl")
    assert report.summary.log_format == "codex"
    assert report.summary.steps > 5
    assert report.findings and report.explanations
    assert report.agents_md.startswith("# Agent Rules")
    assert report.provider == "mock" and report.provider_is_mock is True
    assert report.summary.file_name == "codex_session.jsonl"


def test_claude_session_end_to_end():
    report = run(CLAUDE)
    assert report.summary.log_format == "claude"
    assert {"retry", "reverted_edit"} <= {finding.type for finding in report.findings}
    assert report.explanations


def test_explanations_match_deterministic_findings():
    report = run(CLAUDE)
    for explanation in report.explanations:
        matching = [f for f in report.findings if f.type == explanation.issue_type]
        assert matching, explanation.issue_type
        assert explanation.severity in {f.severity for f in matching}
        assert explanation.steps in [list(f.steps) for f in matching]


def test_steps_are_returned_with_issue_types():
    report = run(CLAUDE)
    assert report.steps
    flagged = [step for step in report.steps if step.issue_types]
    assert flagged, "at least one step should be linked to a finding"
    assert all(step.id is not None for step in report.steps)


def test_broken_lines_do_not_break_the_run():
    payload = "\n".join([
        json.dumps({"type": "user", "content": "go"}),
        "{ broken",
        "plain text",
        json.dumps({"type": "assistant", "content": "ok"}),
    ])
    report = run(payload)
    assert report.summary.invalid_lines == 2
    assert report.summary.steps == 2


def test_empty_input_is_handled():
    report = run("")
    assert report.summary.steps == 0
    assert report.findings == [] and report.explanations == []
    assert report.warnings


def test_max_issues_limits_llm_calls():
    report = run(CODEX, max_issues=2)
    assert len(report.explanations) <= 2
    assert report.summary.issues_total > len(report.explanations)


def test_explanations_can_be_disabled():
    report = run(CODEX, max_issues=0)
    assert report.explanations == []
    assert report.findings


def test_only_local_context_reaches_the_llm():
    """The provider must never see the whole session log."""
    captured = []

    class CapturingProvider:
        name = "capture"

        async def generate_issue_explanation(self, issue):
            captured.append(issue)
            return MockLLMProvider().build(issue)

    run(CODEX, service=LLMService(CapturingProvider()))
    assert captured
    for issue in captured:
        assert issue.context
        assert len(issue.context) <= 3000
        assert issue.context.count("Step ") <= 12


def test_provider_failure_is_reported_not_hidden():
    class BrokenProvider:
        name = "openai-compatible"

        async def generate_issue_explanation(self, issue):
            raise RuntimeError("upstream 500")

    report = run(CODEX, service=LLMService(BrokenProvider(), retries=0, fallback_to_mock=False))
    assert report.explanations == []
    assert report.findings
    assert report.provider == "openai-compatible"
    assert any("explanation" in warning.lower() for warning in report.warnings)


def test_mock_fallback_is_labelled_as_mock():
    class BrokenProvider:
        name = "openai-compatible"

        async def generate_issue_explanation(self, issue):
            raise RuntimeError("upstream 500")

    report = run(CODEX, service=LLMService(BrokenProvider(), retries=0, fallback_to_mock=True))
    assert report.explanations
    assert report.provider == "mock-fallback"
    assert report.provider_is_mock is True
    assert any("mock" in warning.lower() for warning in report.warnings)


def test_sync_helper():
    report = analyze_session_sync(CODEX, service=LLMService(MockLLMProvider()))
    assert report.summary.steps > 0


def test_forced_format_is_respected():
    report = run(CLAUDE, log_format="generic")
    assert report.summary.log_format == "generic"


def test_long_session_keeps_every_step_a_finding_points_at():
    from backend.parser import Step
    from backend.services.analysis_pipeline import _steps_out
    from backend.analysis import Finding

    steps = [Step(id=i, event_type="message", actor="agent") for i in range(1000)]
    findings = [Finding(type="retry", severity="high", steps=(700, 950), message="retry")]
    returned = {step.id for step in _steps_out(steps, findings, limit=100)}
    assert {700, 950, 698, 952} <= returned           # flagged steps and their neighbours
    assert min(returned) == 0 and max(returned) > 900  # still spans the whole session
    assert len(returned) <= 110
