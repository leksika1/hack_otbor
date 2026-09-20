"""Public service of the LLM layer.

Usage from the rest of the backend::

    issues = analyzer.analyze(steps)
    service = LLMService()                      # provider picked from env
    explanations = await service.explain_issues(issues)
    agents_md = generate_agents_md(explanations)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Sequence

from .provider import LLMProvider, MockLLMProvider, get_default_provider
from .schemas import Issue, IssueExplanation

__all__ = ["LLMService"]

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4


class LLMService:
    """Turns analyzer issues into human-readable explanations.

    Parameters
    ----------
    provider:
        Anything implementing ``LLMProvider``. Defaults to
        ``get_default_provider()`` (real provider if ``LLM_API_KEY`` is set,
        otherwise ``MockLLMProvider``).
    concurrency:
        Maximum number of parallel LLM requests.
    retries:
        Extra attempts after the first failure (deliberately kept simple).
    fallback_to_mock:
        When True (default) a failed issue still gets a deterministic
        explanation from ``MockLLMProvider`` instead of disappearing from the
        report. When False, failed issues are skipped.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        retries: int = 1,
        fallback_to_mock: bool = True,
    ) -> None:
        self.provider: LLMProvider = provider or get_default_provider()
        self.concurrency = max(1, int(concurrency))
        self.retries = max(0, int(retries))
        self.fallback_to_mock = fallback_to_mock
        self._mock = MockLLMProvider()

    # ------------------------------------------------------------------ #

    async def explain_issue(self, issue: Issue) -> IssueExplanation:
        """Explain a single issue. Raises if the provider fails and no fallback."""
        issue = self._coerce(issue)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                result = await self.provider.generate_issue_explanation(issue)
                return self._enforce_deterministic_fields(issue, result)
            except Exception as exc:  # noqa: BLE001 - provider errors are opaque
                last_error = exc
                logger.warning(
                    "LLM provider failed for issue %s (attempt %s/%s): %s",
                    issue.type, attempt + 1, self.retries + 1, exc,
                )
        if self.fallback_to_mock:
            logger.warning("Falling back to MockLLMProvider for issue %s", issue.type)
            return self._mock.build(issue)
        raise last_error if last_error else RuntimeError("unknown LLM failure")

    async def explain_issues(
        self,
        issues: Sequence[Issue] | Iterable[Issue] | None,
        *,
        sort_by_severity: bool = False,
    ) -> list[IssueExplanation]:
        """Explain many issues concurrently.

        * an empty or ``None`` input returns ``[]``;
        * one failing request never breaks the others;
        * input order is preserved unless ``sort_by_severity`` is set.
        """
        items = [self._coerce(issue) for issue in (issues or [])]
        if not items:
            return []

        semaphore = asyncio.Semaphore(self.concurrency)

        async def run(issue: Issue) -> IssueExplanation | None:
            async with semaphore:
                try:
                    return await self.explain_issue(issue)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Skipping issue %s: %s", issue.type, exc)
                    return None

        results = await asyncio.gather(*(run(issue) for issue in items), return_exceptions=True)

        explanations: list[IssueExplanation] = []
        for issue, result in zip(items, results):
            if isinstance(result, IssueExplanation):
                explanations.append(result)
            elif isinstance(result, BaseException):
                logger.error("Skipping issue %s: %s", issue.type, result)

        if sort_by_severity:
            explanations.sort(key=lambda item: (item.severity_rank, item.steps[:1]))
        return explanations

    # ------------------------------------------------------------------ #

    @staticmethod
    def _coerce(issue: Any) -> Issue:
        """Accept both ``Issue`` objects and plain dicts from the analyzer."""
        if isinstance(issue, Issue):
            return issue
        return Issue.model_validate(issue)

    @staticmethod
    def _enforce_deterministic_fields(
        issue: Issue, result: IssueExplanation
    ) -> IssueExplanation:
        """The model never owns issue_type / severity / steps."""
        return result.model_copy(
            update={
                "issue_type": issue.type,
                "severity": issue.severity,
                "steps": list(issue.steps),
            }
        )
