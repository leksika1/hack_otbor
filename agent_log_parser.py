"""Crash-free, schema-tolerant JSONL parser for coding-agent logs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class LogStep:
    index: int
    event_type: str = "unknown"
    timestamp: Optional[datetime] = None
    tool_name: Optional[str] = None
    tool_arguments: Any = None
    status: str = "unknown"  # success | error | cancelled | unknown
    text: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    actor: str = "unknown"  # agent | user | system | unknown
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    parse_warnings: tuple[str, ...] = ()

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    step_indices: tuple[int, ...]
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMetrics:
    total_steps: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    token_buckets: list[dict[str, Any]] = field(default_factory=list)
    loops: list[Finding] = field(default_factory=list)
    errors: list[Finding] = field(default_factory=list)
    human_interventions: list[Finding] = field(default_factory=list)
    reverted_edits: list[Finding] = field(default_factory=list)
    idle_periods: list[Finding] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        rank = {"high": 0, "medium": 1, "low": 2}
        return sorted(self.loops + self.errors + self.human_interventions + self.reverted_edits + self.idle_periods,
                      key=lambda x: (rank.get(x.severity, 3), x.step_indices))


class AgentLogParser:
    """Normalizes arbitrary JSONL and computes all metrics deterministically.

    Override :meth:`normalize_event` for a precise Codex/Claude schema. The
    generic adapter intentionally preserves unknown objects as typed steps.
    """
    HUMAN = {"user", "human", "user_message", "input", "interrupt", "approval", "feedback"}
    EDIT = {"write", "write_file", "edit", "replace", "apply_patch", "patch"}
    UNDO = {"undo", "revert", "rollback", "git_reset", "restore", "checkout"}

    def __init__(self, *, similarity_threshold: float = .88, idle_seconds: float = 60, bucket_size: int = 50):
        self.similarity_threshold = max(0., min(1., similarity_threshold))
        self.idle_seconds, self.bucket_size = max(0., idle_seconds), max(1, bucket_size)
        self.steps: list[LogStep] = []
        self.metrics = SessionMetrics()

    def parse_file(self, path: str | Path, *, encoding: str = "utf-8") -> list[LogStep]:
        try:
            with Path(path).open(encoding=encoding, errors="replace") as f:
                return self.parse_lines(f)
        except (OSError, ValueError) as exc:
            self.steps = []
            self.metrics = SessionMetrics(parse_warnings=[f"Could not read log: {type(exc).__name__}: {exc}"])
            return []

    def parse_lines(self, lines: Iterable[str | bytes]) -> list[LogStep]:
        steps: list[LogStep] = []
        warnings: list[str] = []
        for index, line in enumerate(lines):
            try:
                text = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
                if not text.strip():
                    continue
                event = json.loads(text)
                if not isinstance(event, dict):
                    raise ValueError("JSON event is not an object")
                steps.append(self.normalize_event(event, index))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                warning = f"Line {index}: invalid JSON ({type(exc).__name__})"
                warnings.append(warning)
                steps.append(LogStep(index, "invalid_json", actor="unknown", raw={"line": str(line)[:4096]}, parse_warnings=(warning,)))
            except Exception as exc:  # adapters and hostile iterables must not crash a pipeline
                warning = f"Line {index}: normalization failed ({type(exc).__name__})"
                warnings.append(warning)
                steps.append(LogStep(index, "unparseable_event", raw={}, parse_warnings=(warning,)))
        self.steps = steps
        self.metrics = SessionMetrics(total_steps=len(steps), parse_warnings=warnings)
        return steps

    def normalize_event(self, event: Mapping[str, Any], index: int) -> LogStep:
        """Generic format stub. Implement a vendor adapter by overriding this method."""
        payload = self._map(event.get("payload")) or self._map(event.get("data")) or event
        warnings: list[str] = []
        # Codex desktop rollout JSONL nests actual event semantics in payload.
        # Keep this small adapter here: it is still safe for unfamiliar records.
        if event.get("type") == "event_msg" and payload.get("type") == "item_completed":
            item = self._map(payload.get("item")) or {}
            item_type = str(item.get("type", "item_completed"))
            actor = "user" if item_type.lower() in {"usermessage", "user_message"} else "agent"
            return LogStep(index, item_type.lower(), self._time(event.get("timestamp"), warnings),
                           text=self._content_text(item.get("content")), actor=actor, raw=dict(event), parse_warnings=tuple(warnings))
        if event.get("type") == "response_item" and payload.get("type") in {"function_call", "custom_tool_call"}:
            return LogStep(index, str(payload["type"]), self._time(event.get("timestamp"), warnings),
                           tool_name=self._string(payload, "name"), tool_arguments=self._decode_arguments(payload.get("arguments", payload.get("input"))),
                           status=self._tool_status(payload), actor="agent", raw=dict(event), parse_warnings=tuple(warnings))
        if event.get("type") == "response_item" and payload.get("type") == "message":
            role = str(payload.get("role", "unknown")).lower()
            return LogStep(index, "message", self._time(event.get("timestamp"), warnings),
                           text=self._content_text(payload.get("content")), actor="user" if role == "user" else "agent",
                           raw=dict(event), parse_warnings=tuple(warnings))
        if event.get("type") == "event_msg" and payload.get("type") == "task_complete":
            error = self._map(payload.get("error"))
            return LogStep(index, "task_complete", self._time(event.get("timestamp"), warnings),
                           status="error" if error else "success", actor="agent", raw=dict(event), parse_warnings=tuple(warnings))
        typ = self._string(event, "type", "event_type", "kind", "role") or "unknown"
        tool = self._string(payload, "tool_name", "tool", "name", "command_name") or self._string(event, "tool_name", "tool")
        args = self._value(payload, "tool_input", "arguments", "input", "params", "parameters")
        timestamp = self._time(self._value(event, "timestamp", "time", "created_at", "createdAt", "ts"), warnings)
        usage = self._map(payload.get("usage")) or self._map(event.get("usage")) or {}
        role = (self._string(event, "role", "actor", "author", "source") or typ).lower()
        actor = "user" if role in self.HUMAN or "user" in role or "human" in role else ("agent" if role in {"assistant", "agent", "model", "tool"} else "unknown")
        raw_status = str(self._value(payload, "status", "result", "outcome") or self._value(event, "status", "result", "outcome") or "").lower()
        status = "error" if raw_status in {"error", "failed", "failure", "exception", "timeout"} or self._error(event) else ("success" if raw_status in {"success", "ok", "completed", "done"} else ("cancelled" if "cancel" in raw_status else "unknown"))
        return LogStep(index=index, event_type=typ.lower(), timestamp=timestamp, tool_name=tool, tool_arguments=args,
                       status=status, text=self._string(payload, "text", "content", "message", "summary"),
                       input_tokens=self._int(usage.get("input_tokens", usage.get("prompt_tokens", event.get("input_tokens", 0)))),
                       output_tokens=self._int(usage.get("output_tokens", usage.get("completion_tokens", event.get("output_tokens", 0)))),
                       cost=self._float(usage.get("cost", usage.get("cost_usd", event.get("cost", event.get("cost_usd", 0))))),
                       actor=actor, raw=dict(event), parse_warnings=tuple(warnings))

    def analyze(self, steps: Optional[Sequence[LogStep]] = None) -> SessionMetrics:
        source = list(self.steps if steps is None else steps)
        m = SessionMetrics(len(source), sum(x.tokens for x in source), sum(x.cost for x in source))
        m.parse_warnings = [w for x in source for w in x.parse_warnings]
        m.token_buckets = [{"step_range": (part[0].index, part[-1].index), "tokens": sum(x.tokens for x in part), "cost": sum(x.cost for x in part)} for part in (source[i:i+self.bucket_size] for i in range(0, len(source), self.bucket_size))]
        m.loops = self._loops(source); m.errors = self._errors(source)
        m.human_interventions = [Finding("human_intervention", "medium", (x.index,), "Human input or control event detected.", {"event_type": x.event_type}) for x in source if x.actor == "user"]
        m.reverted_edits = self._reverts(source); m.idle_periods = self._idle(source)
        self.metrics = m
        return m

    def get_llm_chunks(self, max_tokens: int) -> list[dict[str, Any]]:
        """Bounded JSON context for a later LLM call; this method never calls one."""
        if max_tokens < 128: raise ValueError("max_tokens must be at least 128")
        if self.steps and not self.metrics.total_steps: self.analyze()
        chunks: list[dict[str, Any]] = []; current = {"metrics": self._safe(asdict(self.metrics)), "steps": []}
        for step in self.steps:
            compact = self._compact(step); candidate = {**current, "steps": current["steps"] + [compact]}
            if current["steps"] and self._estimate(candidate) > max_tokens:
                chunks.append(current); current = {"metrics": {"continuation": True}, "steps": [compact]}
            else:
                if not current["steps"] and self._estimate(candidate) > max_tokens: compact["raw_preview"] = compact["raw_preview"][:max_tokens * 2]
                current = candidate
        chunks.append(current)
        return [{"chunk_index": i, "chunk_count": len(chunks), **c} for i, c in enumerate(chunks)]

    def _loops(self, steps: Sequence[LogStep]) -> list[Finding]:
        history: dict[str, list[tuple[LogStep, str]]] = {}; out: list[Finding] = []
        for step in steps:
            if not step.tool_name: continue
            key, signature = step.tool_name.lower(), self._canon(step.tool_arguments)
            for before, old in history.get(key, [])[-8:]:
                ratio = SequenceMatcher(None, old, signature).ratio()
                if ratio >= self.similarity_threshold:
                    out.append(Finding("loop", "high" if ratio == 1 else "medium", (before.index, step.index), f"Tool '{step.tool_name}' repeated with {'identical' if ratio == 1 else 'very similar'} arguments.", {"tool": step.tool_name, "similarity": round(ratio, 3)})); break
            history.setdefault(key, []).append((step, signature))
        return out

    def _errors(self, steps: Sequence[LogStep]) -> list[Finding]:
        failed: dict[tuple[str, str], LogStep] = {}; out: list[Finding] = []
        for step in steps:
            if step.status != "error" and not self._error(step.raw): continue
            error = self._error(step.raw)
            # A task/session failure is useful evidence, but not a tool retry.
            # Never merge separate turns that happened to end with the same error.
            if not step.tool_name:
                out.append(Finding("session_error", "high", (step.index,), "Session/turn ended with an error.", {"error": error[:500]}))
                continue
            key = ((step.tool_name or step.event_type).lower(), self._canon(step.tool_arguments)); prior = failed.get(key)
            out.append(Finding("tool_retry" if prior else "tool_error", "high" if prior else "medium", (prior.index, step.index) if prior else (step.index,), f"{'Retry after failed' if prior else 'Failed'} tool/event '{step.tool_name or step.event_type}'.", {"error": error[:500]})); failed[key] = step
        return out

    def _reverts(self, steps: Sequence[LogStep]) -> list[Finding]:
        edits: list[LogStep] = []; out: list[Finding] = []
        for step in steps:
            tool = (step.tool_name or "").lower()
            if tool in self.UNDO and edits: out.append(Finding("reverted_edit", "medium", (edits[-1].index, step.index), "An agent edit appears to have been reverted.", {"undo_tool": step.tool_name}))
            elif tool in self.EDIT: edits.append(step)
        return out

    def _idle(self, steps: Sequence[LogStep]) -> list[Finding]:
        timed = [x for x in steps if x.timestamp]; out: list[Finding] = []
        for before, after in zip(timed, timed[1:]):
            seconds = (after.timestamp - before.timestamp).total_seconds()  # type: ignore[operator]
            if seconds >= self.idle_seconds: out.append(Finding("idle_period", "high" if seconds >= self.idle_seconds * 5 else "low", (before.index, after.index), f"{seconds:.0f}s elapsed between recorded steps.", {"seconds": seconds}))
        return out

    @staticmethod
    def _map(value: Any) -> Optional[Mapping[str, Any]]: return value if isinstance(value, Mapping) else None
    @staticmethod
    def _value(data: Mapping[str, Any], *keys: str) -> Any: return next((data[k] for k in keys if data.get(k) is not None), None)
    @classmethod
    def _string(cls, data: Mapping[str, Any], *keys: str) -> Optional[str]:
        value = cls._value(data, *keys); return str(value) if isinstance(value, (str, int, float)) else None
    @staticmethod
    def _int(value: Any) -> int:
        try: return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError): return 0
    @staticmethod
    def _float(value: Any) -> float:
        try: return max(0., float(value or 0))
        except (TypeError, ValueError, OverflowError): return 0.
    @staticmethod
    def _time(value: Any, warnings: list[str]) -> Optional[datetime]:
        try:
            if value is None: return None
            if isinstance(value, (int, float)): return datetime.fromtimestamp(float(value) / (1000 if value > 10_000_000_000 else 1), timezone.utc)
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00")); return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError): warnings.append("Unparseable timestamp"); return None
    @staticmethod
    def _error(event: Mapping[str, Any]) -> str:
        for scope in (event, AgentLogParser._map(event.get("payload")) or {}):
            for key in ("error", "stderr", "exception", "failure_reason"):
                if scope.get(key): return str(scope[key])
        return ""
    @staticmethod
    def _decode_arguments(value: Any) -> Any:
        if not isinstance(value, str): return value
        try: return json.loads(value)
        except json.JSONDecodeError: return value
    @staticmethod
    def _content_text(value: Any) -> Optional[str]:
        if isinstance(value, str): return value
        if isinstance(value, list):
            return "\n".join(str(x.get("text", "")) for x in value if isinstance(x, Mapping)) or None
        return None
    @staticmethod
    def _tool_status(payload: Mapping[str, Any]) -> str:
        value = str(payload.get("status", "")).lower()
        if value in {"error", "failed", "failure", "exception", "timeout"}: return "error"
        if value in {"completed", "success", "ok"}: return "success"
        if "cancel" in value: return "cancelled"
        return "unknown"
    @staticmethod
    def _canon(value: Any) -> str:
        try: return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))[:20000]
        except (TypeError, ValueError): return repr(value)[:20000]
    def _compact(self, s: LogStep) -> dict[str, Any]: return {"index": s.index, "event_type": s.event_type, "timestamp": s.timestamp.isoformat() if s.timestamp else None, "tool_name": s.tool_name, "arguments": self._safe(s.tool_arguments), "status": s.status, "actor": s.actor, "tokens": s.tokens, "cost": s.cost, "text": s.text, "raw_preview": str(self._safe(s.raw))[:2000]}
    @staticmethod
    def _safe(value: Any) -> Any:
        if isinstance(value, datetime): return value.isoformat()
        if isinstance(value, Mapping): return {str(k): AgentLogParser._safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)): return [AgentLogParser._safe(v) for v in value]
        return value if isinstance(value, (str, int, float, bool)) or value is None else repr(value)
    @staticmethod
    def _estimate(value: Any) -> int: return max(1, len(json.dumps(value, ensure_ascii=False, default=str)) // 3)
