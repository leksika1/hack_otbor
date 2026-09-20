"""LLM layer: turns analyzer issues into explanations and AGENTS.md rules.

Public API::

    from backend.llm import (
        Issue, IssueEvidence, IssueExplanation,
        LLMService, LLMProvider, MockLLMProvider, OpenAICompatibleProvider,
        get_default_provider, generate_agents_md, save_agents_md,
    )
"""

from .agents_md import generate_agents_md, save_agents_md
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .providers import (
    LLMProvider,
    LLMProviderError,
    MockLLMProvider,
    OpenAICompatibleProvider,
    get_default_provider,
    parse_llm_output,
)
from .schemas import (
    SEVERITY_ORDER,
    Issue,
    IssueEvidence,
    IssueExplanation,
    LLMOutput,
)
from .service import LLMService

__all__ = [
    "Issue",
    "IssueEvidence",
    "IssueExplanation",
    "LLMOutput",
    "SEVERITY_ORDER",
    "LLMProvider",
    "LLMProviderError",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "get_default_provider",
    "parse_llm_output",
    "LLMService",
    "generate_agents_md",
    "save_agents_md",
    "SYSTEM_PROMPT",
    "build_user_prompt",
]

__version__ = "0.1.0"
