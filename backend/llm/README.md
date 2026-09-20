# LLM layer

Turns issues found by the deterministic analyzers into human-readable
explanations and ready-to-paste `AGENTS.md` rules.

```
Issue[]  ->  LLMService.explain_issues()  ->  IssueExplanation[]  ->  generate_agents_md()
```

The LLM never sees the whole log and never searches for problems itself: it
receives one already-detected issue plus its evidence and a small context
fragment.

## Integration

```python
from backend.llm import LLMService, generate_agents_md, save_agents_md

issues = findings_to_issues(metrics.findings, steps)   # see backend/analysis
service = LLMService()                    # provider chosen from env vars
explanations = await service.explain_issues(issues, sort_by_severity=True)
agents_md = generate_agents_md(explanations)
save_agents_md(explanations, "AGENTS.md")
```

`LLMService` accepts both `Issue` objects and plain dicts, so the analyzer can
keep its own model as long as the fields line up (`type`, `severity`, `steps`,
`evidence`, `context`).

## Configuration

```
LLM_API_KEY=            # if empty -> MockLLMProvider, everything works offline
LLM_BASE_URL=           # optional, any OpenAI-compatible endpoint
LLM_MODEL=              # optional, defaults to gpt-4o-mini
LLM_FALLBACK_TO_MOCK=   # false by default: a failed LLM call is reported, not faked
LLM_MAX_ISSUES=         # how many issues the pipeline explains per session
```

`LLMService.provider_name` / `used_mock` tell the caller which provider
actually produced the explanations (`mock`, `openai-compatible`, or
`mock-fallback` when a real call failed and the fallback was enabled).

## Anti-hallucination

`issue_type`, `severity` and `steps` are always taken from the source `Issue`,
never from the model (`LLMService._enforce_deterministic_fields`). The model
only produces `title`, `explanation`, `impact`, `recommendation`, `agent_rule`.

## Demo and tests

```
python -m backend.llm.demo          # mock provider, prints explanations + AGENTS.md
pytest                              # no API key needed
```
