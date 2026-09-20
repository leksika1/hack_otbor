# Coding-agent session analyzer

Upload a Codex / Claude Code session log (`.jsonl`) and get back what went
wrong in that session: repeated tool calls, failures and retries, user
corrections, idle gaps, token hotspots - each one tied to concrete step
numbers, explained in plain language, with a ready-to-paste `AGENTS.md` rule.

```
JSONL log
   -> Parser            (agent_log_parser.py)      normalized steps
   -> Deterministic analysis                        Finding[]
   -> Adapter                                       Issue[]
   -> Context builder                               Issue[] + small log window
   -> LLM layer         (backend/llm)               Explanation[]
   -> Report                                        summary + findings + AGENTS.md
```

## Why the LLM does not read the whole log

The Python code finds the problems; the LLM only explains them.

* **Deterministic metrics.** Repetition, failures, retries, idle time and token
  usage are counted by code, so the same log always produces the same findings.
* **Fewer hallucinations.** The model receives one already-detected issue with
  its evidence, not a haystack to search - it cannot invent a problem that the
  analyzer never saw.
* **Lower token usage.** A 100 MB rollout never reaches the model. Only a few
  steps around each finding do, and only for the top `LLM_MAX_ISSUES` issues.
* **Traceability.** `issue_type`, `severity` and `steps` are taken from the
  analyzer *after* the model answers, so every sentence in the report can be
  traced back to specific steps in the log.

## Setup

### Local

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # works without an API key too
uvicorn backend.api:app --reload
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Then open <http://localhost:8000/docs> (Swagger UI) or
<http://localhost:8000/health>.

The React dashboard in `frontend/` is optional and runs as a second service:

```bash
docker compose --profile frontend up --build    # backend :8000 + dashboard :5173
```

Locally it is the usual `cd frontend && npm install && npm run dev`. It posts to
`http://127.0.0.1:8000/api/analyze`, which is served by the same backend.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_API_KEY` | *(empty)* | Key for an OpenAI-compatible API. Empty = offline mock provider. |
| `LLM_BASE_URL` | *(empty)* | Optional custom endpoint (OpenRouter, vLLM, a local proxy). |
| `LLM_MODEL` | `gpt-4o-mini` | Model name passed to the provider. |
| `LLM_FALLBACK_TO_MOCK` | `false` | `true` replaces failed LLM calls with mock text (development only). |
| `LLM_MAX_ISSUES` | `5` | How many of the most significant issues are explained by the LLM. |
| `LLM_CONTEXT_RADIUS` | `2` | Steps included around each flagged step. |
| `LLM_CONCURRENCY` | `4` | Parallel LLM requests. |
| `MAX_UPLOAD_BYTES` | `26214400` | Upload size limit for `POST /analyze`. |

Never commit a real key: `.env` is git-ignored, `.env.example` is not.

## API

### `GET /health`

```json
{"status": "ok", "llm_configured": false, "provider": "mock",
 "model": "gpt-4o-mini", "fallback_to_mock": false}
```

### `POST /analyze`

Multipart upload of a `.jsonl` log.

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@rollout.jsonl"

# deterministic report only, no LLM calls
curl -X POST "http://localhost:8000/analyze?explain=false" -F "file=@rollout.jsonl"
```

```json
{
  "summary": {"steps": 842, "tokens": 135000, "issues_total": 12,
              "issues_explained": 5, "parse_warnings": 2, "invalid_lines": 2},
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
  "agents_md": "# Agent Rules\n\n## Repository exploration\n\n- ...",
  "provider": "openai-compatible",
  "provider_is_mock": false,
  "warnings": []
}
```

Errors: `400` empty upload, `413` too large, `422` no valid JSON lines,
`500` unexpected failure. A few broken lines inside a valid log are *not* an
error - they are counted in `summary.invalid_lines` and reported in `warnings`.

### `POST /api/analyze`

Same analysis as `/analyze`, plus the camelCase aliases the React dashboard
reads (`summary.fileName`, `summary.duration`, `summary.totalTokens`,
`summary.totalCost`, `metrics[]`, `logSteps[]`, `artifactText`). It exists so
that the frontend and the canonical API can evolve independently.

### `POST /generate-agents-md`

```bash
curl -X POST http://localhost:8000/generate-agents-md \
  -H 'Content-Type: application/json' \
  -d '{"explanations": [ ... ]}'
```

### CLI

```bash
python -m backend.cli path/to/rollout.jsonl
python -m backend.cli path/to/rollout.jsonl --json --agents-md AGENTS.md
```

## Tests

```bash
pytest
```

No API key required: the suite runs entirely on `MockLLMProvider`.

## Project structure

```
agent_log_parser.py          parser + deterministic analyzers (shared module, root by design)

backend/
    api.py                   FastAPI app: /health, /analyze, /api/analyze, /generate-agents-md
    pipeline.py              orchestration: JSONL -> findings -> issues -> LLM -> report
    dashboard.py             view-model for the React frontend (no frontend code changes)
    cli.py                   python -m backend.cli <log.jsonl>
    config.py                environment configuration
    parser/
        __init__.py          facade over the root-level parser module
        adapter.py           SessionParser: Codex tool-output and token-count events
    analysis/
        adapters.py          Finding -> Issue mapping (FINDING_TYPE_MAP)
        context.py           build_issue_context / enrich_issues_with_context
    llm/
        schemas.py           Issue / IssueExplanation contracts
        prompts.py           system prompt + JSON schema
        provider.py          LLMProvider protocol, MockLLMProvider, OpenAI-compatible
        service.py           LLMService.explain_issue / explain_issues
        agents_md.py         AGENTS.md generation
        examples.py demo.py  offline demo data and runner

frontend/                    React + Vite dashboard (developed separately, untouched here)

tests/                       pytest suite (parser, adapters, context, pipeline, dashboard, API, LLM)
    test_agent_log_parser.py the parser's own unittest suite
tests/fixtures/              small Codex-shaped sample log
```

`agent_log_parser.py` intentionally stays at the repository root: it is
developed in parallel, and `backend/parser/` is only a thin facade over it.

## LLM providers: real vs mock

| | `MockLLMProvider` | `OpenAICompatibleProvider` |
| --- | --- | --- |
| Needs `LLM_API_KEY` | no | yes |
| Output | deterministic templates built from the evidence | model-generated |
| Used when | no key configured, tests, frontend work, demos | `LLM_API_KEY` is set |

Every response carries `provider` and `provider_is_mock`, so mock output is
never presented as a real answer. If a real call fails and
`LLM_FALLBACK_TO_MOCK=false` (the default), the deterministic findings are
still returned, `explanations` stays empty and the reason appears in
`warnings`. With `LLM_FALLBACK_TO_MOCK=true` the mock fills in and `provider`
becomes `mock-fallback`.

## Limitations

* Best supported format: Codex desktop rollout JSONL (`event_msg` /
  `response_item` records). Other logs go through a generic, schema-tolerant
  adapter - fields it cannot recognise are preserved but not interpreted.
* Repetition detection is a text-similarity heuristic (`SequenceMatcher`), and
  token hotspots are "bucket above 2x the session average". Both are
  approximations, deliberately simple and explainable.
* Token metrics only exist if the log carries usage data; otherwise token
  hotspots are silently skipped.
* No database, no auth, no persistence - each request is analyzed in memory.
