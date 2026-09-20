"""Post-mortem analysis of coding-agent sessions.

Layers:
    backend.parser    raw JSONL  -> normalized steps
    backend.analysis  steps      -> deterministic findings -> LLM-ready issues
    backend.llm       issue      -> explanation + AGENTS.md rule
    backend.services  the single orchestration entry point
    backend.api       HTTP layer
"""

__version__ = "1.0.0"
