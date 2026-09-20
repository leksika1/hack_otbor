"""Tests for AGENTS.md generation."""

from __future__ import annotations

import asyncio

from backend.llm import IssueExplanation, LLMService, MockLLMProvider, generate_agents_md, save_agents_md
from backend.llm.agents_md import EMPTY_BODY
from backend.llm.examples import example_issues


def make(issue_type: str, rule: str, severity: str = "high") -> IssueExplanation:
    return IssueExplanation(
        issue_type=issue_type,
        severity=severity,
        steps=[1],
        title="T",
        explanation="E",
        impact="I",
        recommendation="R",
        agent_rule=rule,
    )


def test_generate_agents_md_basic_structure():
    explanations = [
        make("repeated_tool_call", "Do not repeat an identical repository search more than twice."),
        make("tool_failure", "Inspect the cause of a tool failure before retrying the same command."),
    ]
    md = generate_agents_md(explanations)
    assert md.startswith("# Agent Rules")
    assert "## Repository exploration" in md
    assert "## Tool usage" in md
    assert "- Do not repeat an identical repository search more than twice." in md
    assert md.endswith("\n")


def test_duplicate_rules_are_removed():
    explanations = [
        make("repeated_tool_call", "Do not repeat an identical repository search."),
        make("repeated_tool_call", "do not repeat an identical repository search"),
        make("repeated_tool_call", "  Do not repeat an identical   repository search!  "),
    ]
    md = generate_agents_md(explanations)
    assert md.lower().count("do not repeat an identical repository search") == 1


def test_empty_and_whitespace_rules_are_dropped():
    explanations = [
        make("tool_failure", "   "),
        make("tool_failure", "- Inspect the cause of a tool failure."),
    ]
    md = generate_agents_md(explanations)
    bullets = [line for line in md.splitlines() if line.startswith("- ")]
    assert bullets == ["- Inspect the cause of a tool failure."]


def test_rules_are_normalized():
    md = generate_agents_md([make("retry", "* retry at most twice")])
    assert "- Retry at most twice." in md


def test_empty_input_produces_valid_document():
    md = generate_agents_md([])
    assert md.startswith("# Agent Rules")
    assert EMPTY_BODY in md
    assert generate_agents_md(None) == md


def test_flat_list_mode():
    md = generate_agents_md(
        [make("repeated_tool_call", "Rule one."), make("tool_failure", "Rule two.")],
        group_by_section=False,
    )
    assert "##" not in md
    assert "- Rule one." in md and "- Rule two." in md


def test_unknown_issue_type_goes_to_general_section():
    md = generate_agents_md([make("brand_new_type", "Behave well.")])
    assert "## General" in md


def test_save_agents_md_writes_file(tmp_path):
    explanations = asyncio.run(
        LLMService(MockLLMProvider()).explain_issues(example_issues())
    )
    path = tmp_path / "nested" / "AGENTS.md"
    save_agents_md(explanations, path)
    content = path.read_text(encoding="utf-8")
    assert content == generate_agents_md(explanations)
    assert content.startswith("# Agent Rules")
    assert "- " in content


def test_end_to_end_pipeline_contract():
    """analyzer -> LLMService -> AGENTS.md, without parser or analyzer code."""
    explanations = asyncio.run(
        LLMService(MockLLMProvider()).explain_issues(example_issues(), sort_by_severity=True)
    )
    md = generate_agents_md(explanations)
    assert len(explanations) == 4
    assert md.count("- ") >= 4
