"""Finding -> Issue adapter."""

from __future__ import annotations

from backend.analysis import FINDING_TYPE_MAP, finding_to_issue, findings_to_issues
from backend.llm.schemas import Issue
from backend.parser import Finding, LogStep


def test_known_kinds_are_mapped():
    finding = Finding("loop", "high", (42, 45), "Tool 'grep' repeated.", {"tool": "grep", "similarity": 1.0})
    issue = finding_to_issue(finding)
    assert isinstance(issue, Issue)
    assert issue.type == "repeated_tool_call"
    assert issue.severity == "high"
    assert issue.steps == [42, 45]
    evidence = issue.evidence.as_dict()
    assert evidence["tool"] == "grep"
    assert evidence["similarity"] == 1.0
    assert evidence["detector_message"] == "Tool 'grep' repeated."
    assert evidence["detector_kind"] == "loop"


def test_every_analyzer_kind_has_a_mapping():
    for kind in ("loop", "tool_error", "tool_retry", "session_error",
                 "human_intervention", "idle_period", "reverted_edit", "token_hotspot"):
        assert kind in FINDING_TYPE_MAP


def test_unknown_kind_passes_through():
    issue = finding_to_issue(Finding("brand_new_detector", "low", (1,), "msg", {}))
    assert issue.type == "brand_new_detector"


def test_tool_name_is_taken_from_steps_when_missing():
    finding = Finding("tool_error", "medium", (3,), "Failed tool.", {"error": "boom"})
    steps = [LogStep(index=3, event_type="function_call_output", tool_name="pytest")]
    evidence = finding_to_issue(finding, steps).evidence.as_dict()
    assert evidence["tool"] == "pytest"
    assert evidence["error"] == "boom"


def test_dict_findings_are_supported():
    issue = finding_to_issue({"kind": "idle_period", "severity": "low",
                              "step_indices": [7, 8], "message": "idle", "evidence": {"seconds": 90}})
    assert issue.type == "idle_period"
    assert issue.steps == [7, 8]
    assert issue.evidence.as_dict()["seconds"] == 90


def test_broken_finding_does_not_break_the_batch():
    class Exploding:
        kind = "loop"
        severity = "high"

        @property
        def step_indices(self):
            raise RuntimeError("boom")

    issues = findings_to_issues([Exploding(), Finding("idle_period", "low", (1,), "idle", {})])
    assert [issue.type for issue in issues] == ["idle_period"]


def test_empty_evidence_values_are_dropped():
    issue = finding_to_issue(Finding("tool_error", "medium", (1,), "Failed.", {"error": "", "tool": None}))
    evidence = issue.evidence.as_dict()
    assert "error" not in evidence
