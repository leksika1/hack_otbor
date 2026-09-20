"""Tests for the LLM layer. No real API key is required."""

from __future__ import annotations

import asyncio

import pytest

from backend.llm import (
    Issue,
    IssueExplanation,
    LLMProviderError,
    LLMService,
    MockLLMProvider,
    parse_llm_output,
)
from backend.llm.examples import example_issues


def run(coro):
    return asyncio.run(coro)


ISSUE = Issue(
    type="repeated_tool_call",
    severity="high",
    steps=[42, 43, 44],
    evidence={"tool": "grep", "count": 3},
)


# --- providers ------------------------------------------------------------- #

def test_mock_provider_returns_valid_explanation():
    result = run(MockLLMProvider().generate_issue_explanation(ISSUE))
    assert isinstance(result, IssueExplanation)
    for field in ("title", "explanation", "impact", "recommendation", "agent_rule"):
        assert getattr(result, field).strip()
    assert "grep" in result.explanation


def test_mock_provider_is_deterministic():
    first = run(MockLLMProvider().generate_issue_explanation(ISSUE))
    second = run(MockLLMProvider().generate_issue_explanation(ISSUE))
    assert first == second


def test_mock_provider_handles_unknown_issue_type():
    issue = Issue(type="some_future_analyzer_type", severity="low", steps=[7],
                  evidence={"whatever": 1})
    result = run(MockLLMProvider().generate_issue_explanation(issue))
    assert result.issue_type == "some_future_analyzer_type"
    assert result.agent_rule.strip()


def test_all_example_issues_are_explained():
    explanations = run(LLMService(MockLLMProvider()).explain_issues(example_issues()))
    assert len(explanations) == len(example_issues())


# --- deterministic fields -------------------------------------------------- #

class LyingProvider:
    """Returns wrong issue_type / severity / steps on purpose."""

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        base = MockLLMProvider().build(issue)
        return base.model_copy(
            update={"issue_type": "hallucinated", "severity": "critical", "steps": [999]}
        )


def test_deterministic_fields_come_from_issue():
    result = run(LLMService(MockLLMProvider()).explain_issue(ISSUE))
    assert result.issue_type == ISSUE.type
    assert result.severity == ISSUE.severity
    assert result.steps == ISSUE.steps


def test_llm_cannot_override_deterministic_fields():
    result = run(LLMService(LyingProvider()).explain_issue(ISSUE))
    assert result.issue_type == "repeated_tool_call"
    assert result.severity == "high"
    assert result.steps == [42, 43, 44]


# --- service behaviour ----------------------------------------------------- #

def test_explain_issues_empty_list():
    assert run(LLMService(MockLLMProvider()).explain_issues([])) == []
    assert run(LLMService(MockLLMProvider()).explain_issues(None)) == []


def test_explain_issues_accepts_plain_dicts():
    explanations = run(
        LLMService(MockLLMProvider()).explain_issues(
            [{"type": "tool_failure", "severity": "high", "steps": [1],
              "evidence": {"tool": "pytest", "error": "ModuleNotFoundError"}}]
        )
    )
    assert len(explanations) == 1
    assert explanations[0].issue_type == "tool_failure"


def test_explain_issues_preserves_order():
    issues = example_issues()
    explanations = run(LLMService(MockLLMProvider()).explain_issues(issues))
    assert [item.issue_type for item in explanations] == [item.type for item in issues]


def test_explain_issues_can_sort_by_severity():
    issues = [
        Issue(type="idle_period", severity="low", steps=[1]),
        Issue(type="tool_failure", severity="high", steps=[2]),
        Issue(type="token_hotspot", severity="medium", steps=[3]),
    ]
    explanations = run(
        LLMService(MockLLMProvider()).explain_issues(issues, sort_by_severity=True)
    )
    assert [item.severity for item in explanations] == ["high", "medium", "low"]


class FlakyProvider:
    """Fails for one specific issue type, works for everything else."""

    def __init__(self, failing_type: str = "tool_failure") -> None:
        self.failing_type = failing_type
        self.calls = 0

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        self.calls += 1
        if issue.type == self.failing_type:
            raise LLMProviderError("boom")
        return MockLLMProvider().build(issue)


def test_provider_error_does_not_break_other_issues():
    issues = example_issues()
    service = LLMService(FlakyProvider(), retries=0, fallback_to_mock=False)
    explanations = run(service.explain_issues(issues))
    assert len(explanations) == len(issues) - 1
    assert all(item.issue_type != "tool_failure" for item in explanations)


def test_provider_error_falls_back_to_mock():
    issues = example_issues()
    service = LLMService(FlakyProvider(), retries=0, fallback_to_mock=True)
    explanations = run(service.explain_issues(issues))
    assert len(explanations) == len(issues)
    failed = [item for item in explanations if item.issue_type == "tool_failure"][0]
    assert failed.agent_rule.strip()


def test_retry_is_attempted_once():
    provider = FlakyProvider()
    service = LLMService(provider, retries=1, fallback_to_mock=True)
    run(service.explain_issue(Issue(type="tool_failure", severity="high", steps=[1])))
    assert provider.calls == 2


# --- malformed model output ------------------------------------------------ #

class BrokenJSONProvider:
    """Simulates a model that returns text instead of the expected JSON."""

    def __init__(self, raw: str) -> None:
        self.raw = raw

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        from backend.llm.schemas import IssueExplanation as _Explanation

        output = parse_llm_output(self.raw)
        return _Explanation.from_issue(issue, output)


def test_parse_llm_output_handles_code_fences():
    raw = (
        '```json\n{"title": "T", "explanation": "E", "impact": "I", '
        '"recommendation": "R", "agent_rule": "Do not repeat searches."}\n```'
    )
    output = parse_llm_output(raw)
    assert output.title == "T"
    assert output.agent_rule == "Do not repeat searches."


def test_parse_llm_output_handles_surrounding_prose():
    raw = (
        'Sure! Here is the result:\n{"title": "T", "explanation": "E", "impact": "I", '
        '"recommendation": "R", "agent_rule": "Rule."} Hope this helps.'
    )
    assert parse_llm_output(raw).impact == "I"


@pytest.mark.parametrize("raw", ["", "not json at all", '{"title": "only title"}', "[1, 2, 3]"])
def test_parse_llm_output_rejects_invalid_payloads(raw):
    with pytest.raises(LLMProviderError):
        parse_llm_output(raw)


def test_invalid_llm_json_falls_back_instead_of_crashing():
    service = LLMService(BrokenJSONProvider("sorry, I cannot do that"),
                         retries=0, fallback_to_mock=True)
    result = run(service.explain_issue(ISSUE))
    assert isinstance(result, IssueExplanation)
    assert result.issue_type == ISSUE.type


def test_invalid_llm_json_raises_when_fallback_disabled():
    service = LLMService(BrokenJSONProvider("nope"), retries=0, fallback_to_mock=False)
    with pytest.raises(LLMProviderError):
        run(service.explain_issue(ISSUE))


# --- issue contract flexibility -------------------------------------------- #

def test_issue_accepts_unknown_evidence_fields():
    issue = Issue.model_validate(
        {"type": "human_intervention", "severity": "MEDIUM", "steps": [101],
         "evidence": {"message": "wrong folder", "confidence": 0.9}}
    )
    evidence = issue.evidence.as_dict()
    assert evidence["message"] == "wrong folder"
    assert evidence["confidence"] == 0.9
    assert issue.severity == "medium"


def test_issue_defaults_are_safe():
    issue = Issue.model_validate({"type": "idle_period"})
    assert issue.steps == []
    assert issue.evidence.as_dict() == {}
    result = run(LLMService(MockLLMProvider()).explain_issue(issue))
    assert result.steps == []


def test_prompt_contains_only_the_issue():
    from backend.llm import build_user_prompt

    prompt = build_user_prompt(ISSUE)
    assert "grep" in prompt
    assert "repeated_tool_call" in prompt
    assert len(prompt) < 4000
