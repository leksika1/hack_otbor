"""Deterministic detectors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.analysis import AnalysisConfig, analyze_steps, rank_findings
from backend.parser import SessionParser, Step

CODEX_FIXTURE = Path(__file__).parent / "fixtures" / "codex_session.jsonl"
CLAUDE_FIXTURE = Path(__file__).parent / "fixtures" / "claude_session.jsonl"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def step(step_id, **kwargs):
    kwargs.setdefault("event_type", "tool_call")
    kwargs.setdefault("actor", "agent")
    return Step(id=step_id, **kwargs)


def types(findings):
    return [finding.type for finding in findings]


def analyze(steps, **config):
    return analyze_steps(steps, AnalysisConfig(**config)).findings


# --- repeated tool calls --------------------------------------------------- #

def test_identical_tool_calls_are_flagged_high():
    findings = analyze([step(i, tool_name="grep", tool_arguments={"q": "UserService"}) for i in range(3)])
    repeats = [f for f in findings if f.type == "repeated_tool_call"]
    assert repeats and repeats[0].severity == "high"
    assert repeats[0].steps == (0, 1)
    assert repeats[0].evidence["tool"] == "grep"


def test_different_arguments_are_not_a_repeat():
    findings = analyze([step(0, tool_name="grep", tool_arguments={"q": "alpha"}),
                        step(1, tool_name="grep", tool_arguments={"q": "a completely different query"})])
    assert "repeated_tool_call" not in types(findings)


# --- failures and retries -------------------------------------------------- #

def test_tool_failure_then_retry():
    steps = [
        step(0, tool_name="pytest", tool_arguments={"cmd": "pytest"}, call_id="c1"),
        step(1, event_type="tool_result", tool_name="pytest", call_id="c1", status="error", error="ModuleNotFoundError"),
        step(2, tool_name="pytest", tool_arguments={"cmd": "pytest"}, call_id="c2"),
        step(3, event_type="tool_result", tool_name="pytest", call_id="c2", status="error", error="ModuleNotFoundError"),
    ]
    findings = analyze(steps)
    assert "tool_failure" in types(findings)
    retry = [f for f in findings if f.type == "retry"][0]
    assert retry.steps == (1, 3)
    assert retry.severity == "high"


def test_error_without_a_tool_is_a_session_error():
    findings = analyze([step(0, event_type="task_complete", tool_name=None, status="error", error="quota")])
    assert "session_error" in types(findings)


# --- human interventions --------------------------------------------------- #

def test_first_user_message_is_not_an_intervention():
    findings = analyze([step(0, event_type="user_message", actor="user", tool_name=None, text="do it"),
                        step(1, event_type="message", actor="agent", tool_name=None, text="ok")])
    assert "human_intervention" not in types(findings)


def test_correction_after_agent_work_is_an_intervention():
    findings = analyze([
        step(0, event_type="user_message", actor="user", tool_name=None, text="do it"),
        step(1, event_type="message", actor="agent", tool_name=None, text="working"),
        step(2, event_type="user_message", actor="user", tool_name=None, text="no, wrong folder"),
    ])
    intervention = [f for f in findings if f.type == "human_intervention"][0]
    assert intervention.steps == (2,)
    assert intervention.evidence["message"] == "no, wrong folder"


# --- token hotspots -------------------------------------------------------- #

def test_token_hotspot():
    steps = [step(i, event_type="message", tool_name=None, input_tokens=10) for i in range(20)]
    steps[7] = step(7, event_type="message", tool_name=None, input_tokens=5000)
    findings = analyze(steps, bucket_size=5)
    hotspot = [f for f in findings if f.type == "token_hotspot"][0]
    assert hotspot.evidence["token_count"] >= 5000
    assert hotspot.evidence["ratio"] > 2


def test_no_token_data_means_no_hotspots():
    findings = analyze([step(i, event_type="message", tool_name=None) for i in range(20)], bucket_size=5)
    assert "token_hotspot" not in types(findings)


# --- idle periods ---------------------------------------------------------- #

def test_idle_period():
    steps = [step(0, timestamp=START), step(1, timestamp=START + timedelta(seconds=400))]
    idle = [f for f in analyze(steps, idle_seconds=60) if f.type == "idle_period"][0]
    assert idle.steps == (0, 1)
    assert idle.evidence["duration_seconds"] == 400.0


def test_short_gaps_are_ignored():
    steps = [step(0, timestamp=START), step(1, timestamp=START + timedelta(seconds=5))]
    assert "idle_period" not in types(analyze(steps, idle_seconds=60))


# --- reverted edits -------------------------------------------------------- #

def test_reverted_edit_via_tool_name():
    steps = [step(0, tool_name="edit", tool_arguments={"path": "a.py"}),
             step(1, tool_name="revert", tool_arguments={})]
    assert "reverted_edit" in types(analyze(steps))


def test_reverted_edit_via_shell_command():
    steps = [step(0, tool_name="Edit", tool_arguments={"file_path": "a.py"}),
             step(1, tool_name="Bash", tool_arguments={"command": "git checkout -- a.py"})]
    assert "reverted_edit" in types(analyze(steps))


def test_plain_shell_command_is_not_a_revert():
    steps = [step(0, tool_name="Edit", tool_arguments={"file_path": "a.py"}),
             step(1, tool_name="Bash", tool_arguments={"command": "npm test"})]
    assert "reverted_edit" not in types(analyze(steps))


# --- metrics and ranking --------------------------------------------------- #

def test_metrics():
    steps = [
        step(0, event_type="user_message", actor="user", tool_name=None, timestamp=START),
        step(1, tool_name="grep", input_tokens=10, output_tokens=5),
        step(2, event_type="tool_result", tool_name="grep", status="error", error="x",
             timestamp=START + timedelta(seconds=30)),
    ]
    metrics = analyze_steps(steps).metrics
    assert metrics.total_steps == 3
    assert metrics.total_tokens == 15
    assert metrics.tool_calls == 1
    assert metrics.tool_errors == 1
    assert metrics.user_messages == 1
    assert metrics.duration_seconds == 30.0


def test_findings_are_ranked_by_severity():
    findings = analyze_steps(SessionParser().parse_file(CLAUDE_FIXTURE).steps).findings
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda value: {"high": 0, "medium": 1, "low": 2}[value])
    assert rank_findings(findings) == findings


def test_every_finding_points_at_real_steps():
    for fixture in (CODEX_FIXTURE, CLAUDE_FIXTURE):
        parsed = SessionParser().parse_file(fixture)
        ids = {step.id for step in parsed.steps}
        for finding in analyze_steps(parsed.steps).findings:
            assert finding.steps, finding
            assert set(finding.steps) <= ids, finding


def test_claude_fixture_exercises_the_whole_detector_set():
    parsed = SessionParser().parse_file(CLAUDE_FIXTURE)
    found = set(types(analyze_steps(parsed.steps).findings))
    assert {"repeated_tool_call", "tool_failure", "retry", "human_intervention",
            "idle_period", "reverted_edit", "token_hotspot"} <= found


def test_broken_detector_does_not_break_the_run(monkeypatch=None):
    from backend.analysis import service

    def explode(steps, config):
        raise RuntimeError("boom")

    original = service.DETECTORS
    service.DETECTORS = (("exploding", explode),) + original
    try:
        result = analyze_steps([step(0, tool_name="grep", tool_arguments={})])
        assert result.metrics.total_steps == 1
    finally:
        service.DETECTORS = original
