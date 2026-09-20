# Agent log parser

`agent_log_parser.py` is a crash-free, schema-tolerant JSONL core for Codex- and
Claude Code-like session logs. Every line becomes a strict `LogStep`; unknown
events are preserved and malformed/truncated lines become evidence, never an
exception.

```python
from agent_log_parser import AgentLogParser

parser = AgentLogParser(idle_seconds=60)
steps = parser.parse_file("session.jsonl")
metrics = parser.analyze()
llm_context = parser.get_llm_chunks(max_tokens=8_000)
```

All diagnostics are computed locally and linked to `step_indices`: repeated
tool calls, failures/retries, token/cost buckets, human interventions, edit
reverts, and idle periods. `get_llm_chunks` merely creates bounded JSON
fragments for a later recommendation stage and does not invoke an LLM.

To adapt an exact vendor format, subclass `AgentLogParser` and override
`normalize_event`; the aggregation and safety behavior stay unchanged.
