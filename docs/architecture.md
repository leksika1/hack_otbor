# Architecture notes

## Layers

| Layer | Package | Responsibility | Depends on |
| --- | --- | --- | --- |
| Parsing | `backend.parser` | raw JSONL → `Step[]` | nothing |
| Analysis | `backend.analysis` | `Step[]` → `Finding[]` → `Issue[]` + context | parser, llm.schemas |
| LLM | `backend.llm` | `Issue` → `IssueExplanation`, `AGENTS.md` | core.config |
| Orchestration | `backend.services` | the single `analyze_session` pipeline | all of the above |
| HTTP | `backend.api` | upload handling, schemas, errors | services, core |

Dependencies point in one direction only. The API contains no business logic:
it validates the upload, calls the pipeline and maps failures to status codes.

## Internal contracts

`Step` (parser) is the normalized session event: `id`, `line`, `timestamp`,
`event_type`, `actor`, `tool_name`, `tool_arguments`, `call_id`, `status`,
`text`, `error`, `input_tokens`, `output_tokens`, `cost`, `raw_preview`.
`id` is what every finding refers to; `line` maps back to the physical JSONL
line, because one line can produce several steps.

`Finding` (analysis) is a deterministic detection: `type`, `severity`,
`steps`, `message`, `evidence`. `Issue` (llm.schemas) is the same information
shaped for the model, plus a small `context` string. Both use the same
vocabulary (`ISSUE_TYPES`), so there is no translation table to drift.

`IssueExplanation` is what the model returns. Its `issue_type`, `severity` and
`steps` are overwritten from the source `Issue` after the call
(`LLMService._enforce_deterministic_fields`), so a model cannot rewrite facts.

## Format adapters

Each adapter exposes `matches(event)` and `normalize(event, line, warnings)`.
`SessionParser` decodes lines, samples the first records to pick an adapter and
assigns step ids. Adding a vendor means adding one module.

Notes that the two supported formats forced into the design:

* **Codex.** A `response_item` message with role `user` duplicates the
  `event_msg` user message and carries harness-injected context, so only the
  `event_msg` copy becomes a user step. `token_count` reports either a per-turn
  (`last_token_usage`) or a cumulative (`total_token_usage`) counter; the
  cumulative one is converted to a delta.
* **Claude Code.** The same message is written repeatedly while it streams, so
  `tool_use.id`, `tool_result.tool_use_id` and `uuid` are used to de-duplicate.
  `message.usage` is cumulative per `message.id` and counts four separate input
  categories, so tokens are accumulated as a delta per message id and skipped
  with a warning when there is no id. A `tool_result` has role `user` but is not
  a human turn.
* **Tool status.** The word "error" inside arbitrary tool output is not
  evidence of failure (it appears in source files and test names). Only explicit
  markers count: `is_error`, `success`, `exit_code`, or a
  `Process exited with code N` line.

## Detectors

| Module | Finding type | Rule |
| --- | --- | --- |
| `repeated_calls.py` | `repeated_tool_call` | same tool, argument similarity ≥ 0.88 within a window of 8 calls |
| `failures.py` | `tool_failure`, `retry`, `session_error` | an errored result; a repeat of an already failed command; an error with no tool |
| `interventions.py` | `human_intervention` | a user turn *after* the agent has started working |
| `idle.py` | `idle_period` | ≥ 60 s between recorded steps (`high` at ≥ 5x that) |
| `reverts.py` | `reverted_edit` | an edit tool followed by an undo tool or a `git checkout/reset/revert` shell command |
| `tokens.py` | `token_hotspot` | a step bucket above 2x the session average |

`analyze_steps` runs them all, catching per-detector failures, and ranks the
results by severity. Adding a detector is one entry in `service.DETECTORS`.

## What reaches the LLM

For each selected issue the context builder renders a window of
`LLM_CONTEXT_RADIUS` steps around every flagged step, merges overlapping
windows, marks the flagged lines and truncates the result to 3000 characters.
The prompt contains the issue JSON and that fragment — never the session log.

Volume control before the call: near-duplicate issues (same type and tool)
collapse into one representative with an `occurrences` counter, the rest are
ranked by severity and cut to `LLM_MAX_ISSUES`, and requests run under a
semaphore of `LLM_CONCURRENCY`.

## Failure behaviour

| Failure | Result |
| --- | --- |
| Malformed or truncated line | warning, line counted in `invalid_lines`, parsing continues |
| Unknown event type | step is kept with whatever was recognised |
| Log with no readable steps | `422` from the API |
| Upload over the limit | `413`, the body is never fully buffered |
| Detector raises | logged, other detectors still run |
| LLM invalid JSON / HTTP error | one retry, then the issue is skipped (or mocked if the fallback is on) — always visible in `provider` and `warnings` |
| Unhandled server error | `500` with a generic message; the detail stays in the logs |
