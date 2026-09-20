"""Finding -> Issue projection and top-issue selection."""

from __future__ import annotations

from backend.analysis import Finding, finding_to_issue, findings_to_issues, select_top_issues
from backend.llm.schemas import Issue
from backend.parser import Step


def test_finding_projects_into_an_issue():
    finding = Finding("repeated_tool_call", "high", (42, 45), "Tool 'grep' repeated.",
                      {"tool": "grep", "similarity": 1.0})
    issue = finding_to_issue(finding)
    assert isinstance(issue, Issue)
    assert (issue.type, issue.severity, issue.steps) == ("repeated_tool_call", "high", [42, 45])
    evidence = issue.evidence.as_dict()
    assert evidence["tool"] == "grep"
    assert evidence["similarity"] == 1.0
    assert evidence["detector_message"] == "Tool 'grep' repeated."


def test_tool_name_is_recovered_from_steps():
    finding = Finding("tool_failure", "medium", (3,), "Tool failed.", {"error": "boom"})
    steps = [Step(id=3, event_type="tool_result", tool_name="pytest")]
    assert finding_to_issue(finding, steps).evidence.as_dict()["tool"] == "pytest"


def test_empty_evidence_values_are_dropped():
    issue = finding_to_issue(Finding("tool_failure", "medium", (1,), "Failed.", {"error": "", "tool": None}))
    assert "error" not in issue.evidence.as_dict()


def test_findings_to_issues_keeps_order():
    findings = [Finding("retry", "high", (1,), "a"), Finding("idle_period", "low", (2,), "b")]
    assert [issue.type for issue in findings_to_issues(findings)] == ["retry", "idle_period"]


def test_duplicates_collapse_into_one_representative():
    issues = [Issue(type="repeated_tool_call", severity="medium", steps=[i], evidence={"tool": "grep"})
              for i in range(5)]
    issues.append(Issue(type="idle_period", severity="low", steps=[9]))
    selected = select_top_issues(issues, limit=5)
    assert len(selected) == 2
    repeated = [issue for issue in selected if issue.type == "repeated_tool_call"][0]
    assert repeated.evidence.as_dict()["occurrences"] == 5


def test_selection_is_ordered_by_severity_and_limited():
    issues = [
        Issue(type="idle_period", severity="low", steps=[1]),
        Issue(type="tool_failure", severity="high", steps=[2]),
        Issue(type="token_hotspot", severity="medium", steps=[3]),
    ]
    assert [issue.severity for issue in select_top_issues(issues, 10)] == ["high", "medium", "low"]
    assert len(select_top_issues(issues, 2)) == 2
    assert select_top_issues(issues, 0) == []
