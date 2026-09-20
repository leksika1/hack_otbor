"""Key rotation and endpoint fallback."""

from __future__ import annotations

import asyncio

import pytest

from backend.core.config import _fallbacks, Settings
from backend.llm.providers import FailoverProvider, LLMProviderError, MockLLMProvider
from backend.llm.schemas import Issue

ISSUE = Issue(type="retry", severity="high", steps=[1, 2])


class RateLimited(Exception):
    status_code = 429


class Endpoint:
    def __init__(self, model: str, error: Exception | None = None) -> None:
        self.model, self.error, self.calls = model, error, 0
        self.base_url, self.api_key = None, "k-" + model

    async def generate_issue_explanation(self, issue):
        self.calls += 1
        if self.error:
            raise self.error
        return MockLLMProvider().build(issue)


def test_rate_limited_key_is_benched_and_the_next_one_answers():
    dead, alive = Endpoint("a", RateLimited("429")), Endpoint("b")
    provider = FailoverProvider([dead, alive])
    for _ in range(3):
        asyncio.run(provider.generate_issue_explanation(ISSUE))
    assert (dead.calls, alive.calls) == (1, 3)  # the dead key is not re-tried per request
    assert provider.model == "b" and provider.switches == 1


def test_benched_key_comes_back_after_the_cooldown():
    flaky, spare = Endpoint("a", RateLimited("429")), Endpoint("b", RateLimited("429"))
    provider = FailoverProvider([flaky, spare], cooldown=0)
    with pytest.raises(LLMProviderError):
        asyncio.run(provider.generate_issue_explanation(ISSUE))
    flaky.error = None
    asyncio.run(provider.generate_issue_explanation(ISSUE))
    assert provider.model == "a"


def test_describe_never_exposes_a_whole_key():
    provider = FailoverProvider([Endpoint("a"), Endpoint("b")])
    assert all(len(item["key"]) <= 7 for item in provider.describe())


def test_settings_parse_several_keys_and_fallbacks():
    settings = Settings(llm_api_key="k1, k2,", llm_fallbacks=_fallbacks("http://localhost:8082/v1|Qwen3-4B|local; |gpt-4o-mini|sk"))
    assert settings.llm_api_keys == ("k1", "k2")
    assert settings.llm_fallbacks == (("http://localhost:8082/v1", "Qwen3-4B", "local"), (None, "gpt-4o-mini", "sk"))
