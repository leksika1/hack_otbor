"""LLM providers.

``LLMProvider`` is the only thing ``LLMService`` depends on, so the business
logic is not tied to any vendor SDK.

Two implementations ship here:

* ``MockLLMProvider``      - deterministic, offline, no API key required;
* ``OpenAICompatibleProvider`` - any OpenAI-compatible endpoint, configured
  purely through environment variables.
"""

from __future__ import annotations

import functools
import json
import logging
import time
import os
import re
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from .prompts import RESPONSE_JSON_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from .schemas import Issue, IssueExplanation, LLMOutput

__all__ = [
    "LLMProviderError",
    "LLMProvider",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "parse_llm_output",
    "get_default_provider",
]


logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Raised when a provider could not produce a valid explanation."""


@runtime_checkable
class LLMProvider(Protocol):
    """Contract every provider implements."""

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        ...


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_llm_output(raw: str) -> LLMOutput:
    """Parse a model response into ``LLMOutput``.

    Tolerates code fences and stray prose around the JSON object; raises
    ``LLMProviderError`` when nothing valid can be extracted.
    """
    if not raw or not raw.strip():
        raise LLMProviderError("empty response from LLM")

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()

    candidates = [text]
    match = _JSON_BLOCK.search(text)
    if match and match.group(0) != text:
        candidates.append(match.group(0))

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(data, dict):
            last_error = TypeError("LLM response is not a JSON object")
            continue
        try:
            return LLMOutput.model_validate(data)
        except ValidationError as exc:
            last_error = exc
    raise LLMProviderError(f"could not parse LLM response: {last_error}")


# --------------------------------------------------------------------------- #
# Mock provider
# --------------------------------------------------------------------------- #

def _format_steps(steps: list[int]) -> str:
    if not steps:
        return "the affected steps"
    if len(steps) == 1:
        return f"step {steps[0]}"
    ordered = sorted(steps)
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"steps {ordered[0]}-{ordered[-1]}"
    return "steps " + ", ".join(str(step) for step in ordered)


def _shorten(value: Any, limit: int = 80) -> str:
    text = str(value).strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class MockLLMProvider:
    """Deterministic offline provider.

    Produces a reasonable ``IssueExplanation`` from the issue and its evidence
    alone. Used for tests, frontend development, integration work and as a
    fallback when no API key is configured.
    """

    name = "mock"

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        return self.build(issue)

    # Synchronous entry point, handy in tests and fallbacks.
    def build(self, issue: Issue) -> IssueExplanation:
        evidence = issue.evidence.as_dict()
        builder = self._BUILDERS.get(issue.type, type(self)._generic)
        output = builder(self, issue, evidence)
        return IssueExplanation.from_issue(issue, output)

    # -- per-type builders -------------------------------------------------- #

    def _repeated_tool_call(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        tool = ev.get("tool") or "the same tool"
        count = ev.get("count")
        count_text = f"{count} times" if count else "several times"
        args = ev.get("args")
        args_text = f" with nearly identical arguments ({_shorten(args)})" if args else ""
        return LLMOutput(
            title=f"Repeated {tool} calls",
            explanation=(
                f"At {_format_steps(issue.steps)} the agent called {tool} {count_text}"
                f"{args_text} without changing its strategy in between."
                + self._context_suffix(issue)
            ),
            impact=(
                "Repeating the same call adds tool calls, tokens and wall-clock time "
                "while returning information the agent already had, so the session "
                "makes no measurable progress during those steps."
            ),
            recommendation=(
                f"Review the result of the first {tool} call before issuing another one, "
                "and if it was insufficient change the query or switch to a different "
                "approach instead of repeating it."
            ),
            agent_rule=(
                f"Do not repeat an identical {tool} call more than twice; "
                "review the previous result and change the approach instead."
            ),
        )

    def _tool_failure(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        tool = ev.get("tool") or "a tool"
        error = ev.get("error")
        error_text = f" failing with {_shorten(error)}" if error else " failing"
        count = ev.get("count")
        count_text = f" {count} times" if count else ""
        repeated = isinstance(count, int) and count > 1
        return LLMOutput(
            title=f"Failed {tool} call",
            explanation=(
                f"At {_format_steps(issue.steps)} the agent ran {tool}, "
                f"{error_text.strip()}{count_text}."
                + (" The same command was run again after the failure." if repeated else "")
                + self._context_suffix(issue)
            ),
            impact=(
                "A failing command produces no progress, and running it again before "
                "its cause is resolved spends further tool calls and tokens on the "
                "same error."
            ),
            recommendation=(
                f"Read the {tool} error output and fix its cause "
                "before running the command again."
            ),
            agent_rule=(
                "Inspect the cause of a tool failure and address it before retrying "
                "the same command."
            ),
        )

    def _retry(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        tool = ev.get("tool") or "the same operation"
        count = ev.get("count")
        count_text = f" {count} times" if count else ""
        return LLMOutput(
            title="Unproductive retry loop",
            explanation=(
                f"At {_format_steps(issue.steps)} the agent retried {tool}{count_text} "
                "without an intervening change that could have altered the outcome."
                + self._context_suffix(issue)
            ),
            impact=(
                "Retrying without changing anything spends tool calls and time on an "
                "outcome that is unlikely to differ from the previous attempt."
            ),
            recommendation=(
                "Limit retries and, after the second failed attempt, change the inputs "
                "or the approach rather than repeating the call."
            ),
            agent_rule=(
                "Retry an operation at most twice; after that, change the inputs or "
                "the approach instead of retrying."
            ),
        )

    def _token_hotspot(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        tokens = ev.get("token_count")
        tokens_text = f"about {tokens} tokens" if tokens else "an unusually large amount of context"
        return LLMOutput(
            title="Token-heavy segment",
            explanation=(
                f"{_format_steps(issue.steps).capitalize()} consumed {tokens_text}, "
                "which stands out against the rest of the session."
                + self._context_suffix(issue)
            ),
            impact=(
                "A large amount of context in a narrow range of steps raises cost and "
                "latency and pushes earlier, still relevant information out of the "
                "working context."
            ),
            recommendation=(
                "Read only the parts of a file or command output that are needed, "
                "using ranges or filters instead of loading whole files, and summarize "
                "long output before carrying it forward."
            ),
            agent_rule=(
                "Read files and command output in targeted ranges rather than in full, "
                "and summarize long output before keeping it in context."
            ),
        )

    def _human_intervention(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        message = ev.get("message") or ev.get("user_message")
        message_text = f' The user wrote: "{_shorten(message, 120)}".' if message else ""
        return LLMOutput(
            title="User had to correct the agent",
            explanation=(
                f"At {_format_steps(issue.steps)} the user interrupted the session to "
                f"correct the agent's course.{message_text}"
                + self._context_suffix(issue)
            ),
            impact=(
                "Work done before the correction was based on a wrong assumption, so "
                "the preceding steps were spent on the wrong target and the user had "
                "to spend attention on supervision."
            ),
            recommendation=(
                "Confirm project structure and other key assumptions from the "
                "repository itself before acting on them."
            ),
            agent_rule=(
                "Verify project layout and other key assumptions against the "
                "repository before making changes that depend on them."
            ),
        )

    def _idle_period(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        duration = ev.get("duration_seconds")
        duration_text = f" for about {duration:.0f} seconds" if isinstance(duration, (int, float)) else ""
        return LLMOutput(
            title="Idle period without progress",
            explanation=(
                f"At {_format_steps(issue.steps)} the session showed no recorded "
                f"activity{duration_text}."
                + self._context_suffix(issue)
            ),
            impact=(
                "Time passes without producing output, which lengthens the session "
                "without advancing the task."
            ),
            recommendation=(
                "Break long-running work into observable steps and report intermediate "
                "state instead of leaving the session without recorded activity."
            ),
            agent_rule=(
                "Keep long operations observable by splitting them into steps and "
                "reporting intermediate progress."
            ),
        )

    def _generic(self, issue: Issue, ev: dict[str, Any]) -> LLMOutput:
        readable = issue.type.replace("_", " ")
        ev_text = ", ".join(f"{k}={_shorten(v, 40)}" for k, v in ev.items()) or "no additional evidence"
        return LLMOutput(
            title=readable.capitalize(),
            explanation=(
                f"The analyzer flagged a {readable} issue at {_format_steps(issue.steps)} "
                f"({ev_text})." + self._context_suffix(issue)
            ),
            impact=(
                "The analyzer classified this pattern as inefficient, meaning the "
                f"affected steps likely spent tool calls, tokens or time without a "
                "matching gain in progress."
            ),
            recommendation=(
                "Review the affected steps and adjust the approach so the same pattern "
                "does not repeat in the next session."
            ),
            agent_rule=(
                f"Avoid the {readable} pattern: check previous results before repeating "
                "work and change the approach when progress stalls."
            ),
        )

    @staticmethod
    def _context_suffix(issue: Issue) -> str:
        """Short detector note. The raw log fragment is never echoed back."""
        message = issue.evidence.as_dict().get("detector_message")
        return f" Detector note: {_shorten(message, 160)}" if message else ""

    _BUILDERS = {
        "repeated_tool_call": _repeated_tool_call,
        "tool_failure": _tool_failure,
        "retry": _retry,
        "token_hotspot": _token_hotspot,
        "human_intervention": _human_intervention,
        "idle_period": _idle_period,
    }


# --------------------------------------------------------------------------- #
# Real provider
# --------------------------------------------------------------------------- #

class OpenAICompatibleProvider:
    """Any OpenAI-compatible chat-completions endpoint.

    Configured through environment variables (nothing is hardcoded):

        LLM_API_KEY   - required
        LLM_BASE_URL  - optional (defaults to the official OpenAI endpoint)
        LLM_MODEL     - optional (defaults to ``gpt-4o-mini``)
    """

    name = "openai-compatible"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        temperature: float = 0.2,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL") or None
        self.model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.temperature = temperature
        self.timeout = timeout
        self._client = client
        self._supports_json_schema = True

        if self._client is None and not self.api_key:
            raise LLMProviderError(
                "LLM_API_KEY is not set; use MockLLMProvider or configure the environment"
            )

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # imported lazily, optional dependency
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise LLMProviderError(
                    "the 'openai' package is required for OpenAICompatibleProvider"
                ) from exc
            # max_retries=0: the SDK would silently repeat a 429 twice, burning a
            # daily quota; retrying and failover are decided by the layers above.
            kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout, "max_retries": 0}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        raw = await self._complete(build_user_prompt(issue))
        output = parse_llm_output(raw)
        # The prompt asks for Russian; free models sometimes answer in English anyway.
        # Treat that as a failed attempt so the retry / next endpoint gets a chance.
        if not re.search(r"[а-яё]", output.explanation + output.recommendation, re.IGNORECASE):
            raise LLMProviderError("LLM ignored the requested output language")
        # Deterministic fields are restored from the issue, never from the model.
        return IssueExplanation.from_issue(issue, output)

    async def _complete(self, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if self._supports_json_schema:
                try:
                    return await self._call(messages, self._json_schema_format())
                except Exception as exc:
                    # Only "this endpoint cannot do json_schema" (a 4xx about the
                    # request) justifies a second call; a rate limit or an outage
                    # would fail the same way and just cost another request.
                    if _status_of(exc) not in (400, 404, 415, 422):
                        raise
                    self._supports_json_schema = False
            return await self._call(messages, {"type": "json_object"})
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"LLM request failed: {exc}") from exc

    async def _call(self, messages: list[dict[str, str]], response_format: dict) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format=response_format,
        )
        choices = getattr(response, "choices", None) or []
        content = choices[0].message.content if choices else None
        if not content:
            raise LLMProviderError("LLM returned an empty message")
        return content

    @staticmethod
    def _json_schema_format() -> dict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "issue_explanation",
                "strict": True,
                "schema": RESPONSE_JSON_SCHEMA,
            },
        }


def _status_of(error: BaseException | None) -> int | None:
    """HTTP status behind an SDK or provider error, if there is one."""
    while error is not None:
        status = getattr(error, "status_code", None)
        if isinstance(status, int):
            return status
        error = error.__cause__
    return None


class FailoverProvider:
    """Several endpoints tried in order: spare keys first, then fallbacks.

    An endpoint that answers 429/401/402/403 or cannot be reached is benched for
    ``cooldown`` seconds and the next one takes over; the choice is sticky, so a
    dead key is not re-tried on every request. Each endpoint keeps its own model,
    which is why a local model can be the last resort.
    """

    name = "openai-compatible"
    _BENCH_STATUSES = (401, 402, 403, 429)

    def __init__(self, providers: list[OpenAICompatibleProvider], cooldown: float = 600.0) -> None:
        if not providers:
            raise LLMProviderError("FailoverProvider needs at least one endpoint")
        self.providers = providers
        self.cooldown = cooldown
        self._benched_until: dict[int, float] = {}
        self._current = 0
        self.switches = 0
        self.last_used: OpenAICompatibleProvider | None = None

    @property
    def model(self) -> str:
        return (self.last_used or self.providers[self._current]).model

    def describe(self) -> list[dict[str, Any]]:
        """Endpoint status without secrets - for /health."""
        now = time.monotonic()
        return [
            {"endpoint": item.base_url or "https://api.openai.com/v1", "model": item.model,
             "key": f"...{(item.api_key or '')[-4:]}", "active": index == self._current,
             "benched_seconds": max(0, round(self._benched_until.get(index, 0) - now))}
            for index, item in enumerate(self.providers)
        ]

    async def generate_issue_explanation(self, issue: Issue) -> IssueExplanation:
        last_error: Exception | None = None
        count = len(self.providers)
        for offset in range(count):
            index = (self._current + offset) % count
            if self._benched_until.get(index, 0) > time.monotonic():
                continue
            provider = self.providers[index]
            try:
                result = await provider.generate_issue_explanation(issue)
            except Exception as exc:  # noqa: BLE001 - any endpoint failure moves us on
                last_error = exc
                status = _status_of(exc)
                unreachable = status is None and "connect" in str(exc).lower()
                if status in self._BENCH_STATUSES or (status or 0) >= 500 or unreachable:
                    self._benched_until[index] = time.monotonic() + self.cooldown
                logger.warning("LLM endpoint %s (%s) failed with %s - trying the next one: %s",
                               index + 1, provider.model, status or type(exc).__name__, str(exc)[:160])
                continue
            if index != self._current:
                self.switches += 1
                self._current = index
            self.last_used = provider
            return result
        raise LLMProviderError(f"all {count} LLM endpoints failed or are cooling down: {last_error}")


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def get_default_provider() -> LLMProvider:
    """Real provider when ``LLM_API_KEY`` is set, otherwise the mock one.

    This is what makes the module usable with no external API at all. The
    caller can always tell which one it got through ``provider.name``.
    """
    from backend.core.config import get_settings  # local import keeps the graph flat

    return _provider_for(get_settings())


@functools.lru_cache(maxsize=4)
def _provider_for(settings: Any) -> LLMProvider:
    # Cached per settings so that benched keys stay benched across requests
    # instead of being re-tried by every upload.
    if not settings.has_api_key:
        return MockLLMProvider()
    try:
        endpoints = [
            OpenAICompatibleProvider(api_key=key, base_url=settings.llm_base_url,
                                     model=settings.llm_model, timeout=settings.llm_timeout_seconds)
            for key in settings.llm_api_keys
        ] + [
            OpenAICompatibleProvider(api_key=key, base_url=base_url, model=model,
                                     timeout=settings.llm_timeout_seconds)
            for base_url, model, key in settings.llm_fallbacks
        ]
    except LLMProviderError:
        return MockLLMProvider()
    return endpoints[0] if len(endpoints) == 1 else FailoverProvider(endpoints)
