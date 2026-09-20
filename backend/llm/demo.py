"""Runnable demo of the LLM layer.

    python -m backend.llm.demo            # MockLLMProvider, prints everything
    python -m backend.llm.demo --real     # uses LLM_API_KEY if configured
    python -m backend.llm.demo -o AGENTS.md

No parser, no analyzer and no API key required.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .agents_md import generate_agents_md, save_agents_md
from .examples import example_issues
from .provider import MockLLMProvider, get_default_provider
from .service import LLMService


async def main_async(use_real: bool, out: str | None) -> int:
    provider = get_default_provider() if use_real else MockLLMProvider()
    service = LLMService(provider)

    issues = example_issues()
    print(f"Provider: {getattr(provider, 'name', type(provider).__name__)}")
    print(f"Issues in: {len(issues)}\n")

    explanations = await service.explain_issues(issues, sort_by_severity=True)

    for index, item in enumerate(explanations, start=1):
        print(f"--- [{index}] {item.issue_type} ({item.severity}) steps={item.steps}")
        print(f"title          : {item.title}")
        print(f"explanation    : {item.explanation}")
        print(f"impact         : {item.impact}")
        print(f"recommendation : {item.recommendation}")
        print(f"agent_rule     : {item.agent_rule}")
        print()

    agents_md = generate_agents_md(explanations)
    print("=== AGENTS.md ===")
    print(agents_md)

    if out:
        path = save_agents_md(explanations, Path(out))
        print(f"written to {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM layer demo")
    parser.add_argument("--real", action="store_true", help="use the configured LLM provider")
    parser.add_argument("-o", "--out", help="also write AGENTS.md to this path")
    args = parser.parse_args()
    return asyncio.run(main_async(args.real, args.out))


if __name__ == "__main__":
    sys.exit(main())
