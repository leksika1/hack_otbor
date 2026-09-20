# Agent Session Analyzer

Post-mortem analysis of coding-agent sessions. Upload a Codex or Claude Code
`.jsonl` log and get back what went wrong in that session — repeated tool
calls, failures and retries, user corrections, idle gaps, token hotspots,
reverted edits — each tied to concrete step numbers, explained in plain
language, with a ready-to-paste `AGENTS.md` rule set for the next session.

## What it does

1. **Parses** the raw session log into normalized steps (Codex rollout, Claude
   Code, or a tolerant generic fallback).
2. **Analyzes** those steps with deterministic Python detectors. Every finding
   points at real step ids.
3. **Explains** the most significant findings with an LLM: what happened, why
   it is inefficient, what to do next time, and one standalone agent rule.
4. **Generates** an `AGENTS.md` file from the accumulated rules.

## Architecture

```
JSONL log
   ↓  backend/parser        format adapters → Step[]
Normalized steps
   ↓  backend/analysis      deterministic detectors → Finding[]
Findings (ranked, deduplicated)
   ↓  backend/analysis      top issues + local context window → Issue[]
   ↓  backend/llm           provider → explanation + agent rule
Report + AGENTS.md
```

One orchestration point — `backend.services.analyze_session` — is used by the
API, the CLI and the tests.

## Why deterministic analysis plus an LLM

**Python decides what happened; the LLM only explains why it is inefficient.**

* **Traceable.** Findings are computed by code, so `type`, `severity` and
  `steps` are facts. They are re-applied to the model's answer afterwards, so
  the LLM cannot silently change them.
* **Fewer hallucinations.** The model receives one already-detected issue with
  its evidence and a small window of surrounding steps — not a haystack to
  search in.
* **Lower token usage.** A 100 MB rollout never reaches the model: only a few
  steps around each finding do, for at most `LLM_MAX_ISSUES` issues, with
  near-duplicates collapsed into one request.
* **Works without an API key.** With no key the service runs on a deterministic
  mock provider, and the response always says which provider produced the text.

## Features

* Codex rollout and Claude Code JSONL, with automatic format detection
* Crash-free parsing: malformed, truncated and unknown records become warnings
* Claude streaming de-duplication and cumulative-token accounting
* Detectors: repeated tool calls, tool failures, retries, session errors,
  human interventions, idle periods, reverted edits, token hotspots
* LLM layer with provider abstraction, structured output validation, retry,
  bounded concurrency, and an explicit mock/real distinction
* `AGENTS.md` generation with de-duplicated, grouped rules
* React dashboard: summary, session map, step trace, step inspector, findings
  with explanations, and the generated rules
* FastAPI service with OpenAPI docs, CLI, and Docker Compose deployment

## Project structure

```
backend/
├── api/                    FastAPI layer
│   ├── app.py              application factory, CORS, error handlers
│   ├── routes/             health.py, analysis.py
│   └── schemas.py          HTTP contract
├── core/                   config.py (env), logging.py
├── parser/                 raw JSONL → Step[]
│   ├── models.py           Step, ParseResult, ParseWarning
│   ├── parser.py           line reading, format detection, dispatch
│   ├── codex.py            Codex rollout adapter
│   ├── claude.py           Claude Code adapter
│   └── generic.py          tolerant fallback adapter
├── analysis/               Step[] → Finding[] → Issue[]
│   ├── models.py           Finding, metrics, thresholds
│   ├── service.py          runs every detector, ranks findings
│   ├── repeated_calls.py failures.py interventions.py
│   ├── idle.py reverts.py tokens.py
│   ├── issues.py           Finding → Issue, top-issue selection
│   └── context.py          local context window builder
├── llm/                    Issue → explanation + agent rule
│   ├── schemas.py prompts.py providers.py service.py agents_md.py
├── services/               analysis_pipeline.py, report.py
└── cli.py

frontend/                   React + Vite dashboard (nginx image for production)
tests/                      pytest suite and JSONL fixtures
docs/architecture.md        deeper design notes
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

* Dashboard: <http://localhost:3000>
* API docs: <http://localhost:8000/docs>
* Health: <http://localhost:8000/health>

Then upload a `.jsonl` session log in the UI. Without `LLM_API_KEY` everything
still works — explanations come from the mock provider and the UI labels them
as such.

## Local development

Backend:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn backend.api.app:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
```

CLI (no server needed):

```bash
python -m backend.cli tests/fixtures/codex_session.jsonl
python -m backend.cli session.jsonl --json --agents-md AGENTS.md
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health`, `/api/health` | liveness and which provider is configured |
| `POST` | `/api/analyze` (alias `/analyze`) | upload a `.jsonl` log, get the report |
| `POST` | `/api/agents-md` | render `AGENTS.md` from explanations |

```bash
curl -X POST http://localhost:8000/api/analyze -F "file=@rollout.jsonl"
curl -X POST "http://localhost:8000/api/analyze?explain=false" -F "file=@rollout.jsonl"
```

Query parameters: `log_format` (`auto`, `codex`, `claude`, `generic`),
`max_issues`, `explain`.

```json
{
  "summary": {"file_name": "rollout.jsonl", "log_format": "codex", "steps": 842,
              "tokens": 135000, "cost": 0.0, "duration_seconds": 1830.0,
              "tool_calls": 210, "tool_errors": 12, "user_messages": 6,
              "issues_total": 12, "issues_explained": 5,
              "invalid_lines": 0, "ignored_lines": 31, "parse_warnings": 0},
  "findings": [
    {"type": "repeated_tool_call", "severity": "high", "steps": [42, 48],
     "message": "Tool 'shell' repeated with identical arguments.",
     "evidence": {"tool": "shell", "similarity": 1.0}}
  ],
  "explanations": [
    {"issue_type": "repeated_tool_call", "severity": "high", "steps": [42, 48],
     "title": "...", "explanation": "...", "impact": "...",
     "recommendation": "...", "agent_rule": "..."}
  ],
  "steps": [
    {"id": 42, "line": 51, "timestamp": "2026-01-01T00:00:09+00:00",
     "event_type": "tool_call", "actor": "agent", "tool_name": "shell",
     "status": "unknown", "text": null, "tokens": 0, "cost": 0.0,
     "details": "{...}", "issue_types": ["repeated_tool_call"]}
  ],
  "steps_truncated": false,
  "agents_md": "# Agent Rules\n\n## Repository exploration\n\n- ...",
  "provider": "openai-compatible",
  "provider_is_mock": false,
  "warnings": []
}
```

Errors: `400` empty or unreadable upload, `413` too large, `422` no readable
session steps, `500` unexpected failure (no stack traces are returned). A few
broken lines inside a valid log are not an error — they are counted in
`summary.invalid_lines` and listed in `warnings`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_API_KEY` | *(empty)* | Key for an OpenAI-compatible API; several comma-separated keys rotate (a key answering 429/401 is benched for 10 minutes). Empty = mock provider. |
| `LLM_FALLBACKS` | *(empty)* | Endpoints tried after every key failed: `base_url\|model\|key` separated by `;` (e.g. OpenAI, then a local server). |
| `LLM_BASE_URL` | *(empty)* | Custom endpoint (OpenRouter, vLLM, a local proxy). |
| `LLM_MODEL` | `gpt-4o-mini` | Model name passed to the provider. |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-request timeout. |
| `LLM_FALLBACK_TO_MOCK` | `false` | `true` replaces failed LLM calls with mock text (dev only). |
| `LLM_MAX_ISSUES` | `5` | How many issues are explained per session. |
| `LLM_CONTEXT_RADIUS` | `2` | Steps included around each flagged step. |
| `LLM_CONCURRENCY` | `4` | Parallel LLM requests. |
| `MAX_UPLOAD_BYTES` | `52428800` | Upload limit for `POST /api/analyze`. |
| `MAX_STEPS_IN_RESPONSE` | `500` | Steps returned to the UI. |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed origins. |
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `VITE_API_URL` (frontend) | `/api` | API base path baked into the bundle. |

`.env` is git-ignored; `.env.example` is not. No secrets live in the repository.

## Recommendations as files

Every explanation carries the cause (`cause`) and where the fix belongs
(`fix_kind`: `instruction`, `skill`, `tool`, `hook`, `settings`). From them the
report builds `artifacts` - files ready to drop into the project:

* `AGENTS.md` - de-duplicated rules grouped by topic;
* `CLAUDE.md.append.md` - a block for `CLAUDE.md`, each rule annotated with the steps it came from;
* `.claude/skills/<name>/SKILL.md` - a draft for every `skill` recommendation;
* `NEXT_SESSION.md` - a checklist grouped by kind of fix.

```bash
python -m backend.cli session.jsonl --out-dir ./session-review
```

## Cost

Claude Code logs carry token usage but no prices, so cost is estimated from
`message.model` at API list prices (cache writes 1.25x input, cache reads at
their own rate) and flagged `summary.cost_estimated`. Token hotspots show the
money spent in that stretch (`evidence.cost_usd`).

## LLM providers: real vs mock

| | `MockLLMProvider` | `OpenAICompatibleProvider` |
| --- | --- | --- |
| Needs `LLM_API_KEY` | no | yes |
| Output | deterministic text built from the evidence | model-generated |
| Used when | no key configured, tests, UI work, demos | `LLM_API_KEY` is set |

Every response carries `provider` and `provider_is_mock`, and the dashboard
shows a badge, so mock output is never presented as a real answer. If a real
call fails and `LLM_FALLBACK_TO_MOCK=false` (the default), the deterministic
findings are still returned, `explanations` stays empty and the reason appears
in `warnings`. With the fallback enabled, `provider` becomes `mock-fallback`.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

No API key is required: the suite runs entirely on the mock provider.

## Supported logs

* **Codex desktop rollout JSONL** — best supported. Tool calls, tool outputs
  (exit codes), user messages, per-turn and cumulative token counters, task
  completion errors.
* **Claude Code JSONL** — supported, including streaming duplicates,
  `tool_use` / `tool_result` blocks and cumulative `message.usage` accounting.
* **Anything else** — a generic adapter recognises common field names
  (`type`, `tool_name`, `arguments`, `status`, `usage`, …). Unknown records are
  preserved as steps rather than dropped.

## Limitations

* Detectors are simple, explainable heuristics: text similarity for repeats,
  "above 2x the session average" for token hotspots, a fixed threshold for idle
  gaps. They flag candidates, not proven waste.
* Token metrics only exist when the log carries usage data; otherwise token
  hotspots are skipped rather than guessed.
* Cost is reported only when the log itself contains cost fields — the service
  does not price tokens by model.
* Reverted edits are detected from tool names and shell commands, not from file
  snapshots.
* No database and no auth: each upload is analyzed in memory and nothing is
  stored.
