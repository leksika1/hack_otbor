"""Context window builder."""

from __future__ import annotations

from backend.analysis import build_issue_context, enrich_issues_with_context
from backend.llm.schemas import Issue
from backend.parser import Step


def steps(count: int = 10) -> list[Step]:
    return [
        Step(id=i, event_type="message", text=f"line {i}", actor="agent")
        for i in range(count)
    ]


def test_window_around_a_middle_step():
    context = build_issue_context(Issue(type="x", steps=[5]), steps(), radius=2)
    assert "Step 3" in context and "Step 7" in context
    assert "Step 2" not in context and "Step 8" not in context
    assert "<-- flagged" in context


def test_first_step_does_not_underflow():
    context = build_issue_context(Issue(type="x", steps=[0]), steps(), radius=2)
    assert context.startswith("Step 0")
    assert "Step 2" in context


def test_last_step_does_not_overflow():
    context = build_issue_context(Issue(type="x", steps=[9]), steps(), radius=2)
    assert "Step 7" in context and "Step 9" in context
    assert "Step 10" not in context


def test_overlapping_windows_are_merged():
    context = build_issue_context(Issue(type="x", steps=[4, 5]), steps(), radius=2)
    assert context.count("Step 4") == 1
    assert "..." not in context  # one continuous block, no gap marker


def test_distant_windows_are_separated():
    context = build_issue_context(Issue(type="x", steps=[1, 9]), steps(), radius=1)
    assert "..." in context


def test_missing_step_ids_are_skipped():
    context = build_issue_context(Issue(type="x", steps=[3, 999]), steps(), radius=1)
    assert "Step 3" in context
    assert "999" not in context


def test_no_steps_returns_empty_string():
    assert build_issue_context(Issue(type="x", steps=[1]), [], radius=2) == ""
    assert build_issue_context(Issue(type="x", steps=[]), steps(), radius=2) == ""


def test_context_is_truncated():
    long_steps = [Step(id=i, event_type="message", text="x" * 2000, actor="agent") for i in range(5)]
    context = build_issue_context(Issue(type="x", steps=[2]), long_steps, radius=2, max_chars=500)
    assert len(context) <= 500


def test_tool_calls_are_labelled():
    tool_steps = [
        Step(id=0, event_type="function_call", tool_name="grep", tool_arguments={"q": "UserService"}, actor="agent"),
        Step(id=1, event_type="function_call_output", tool_name="grep", status="error", text="boom", actor="agent"),
    ]
    context = build_issue_context(Issue(type="x", steps=[0]), tool_steps, radius=1)
    assert "[tool_call: grep]" in context
    assert "tool_result: grep (error)" in context


def test_enrich_sets_context_on_copies():
    issues = [Issue(type="x", steps=[2])]
    enriched = enrich_issues_with_context(issues, steps(), radius=1)
    assert issues[0].context is None       # originals untouched
    assert "Step 2" in enriched[0].context


def test_enrich_handles_empty_input():
    assert enrich_issues_with_context([], steps()) == []
    assert enrich_issues_with_context(None, steps()) == []
