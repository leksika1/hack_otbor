"""Prompts for the LLM layer.

Only the issue, its evidence and a small context fragment are sent to the
model. The full session log is never sent.
"""

from __future__ import annotations

import json

from .schemas import Issue

__all__ = [
    "SYSTEM_PROMPT",
    "RESPONSE_JSON_SCHEMA",
    "build_user_prompt",
]

SYSTEM_PROMPT = """\
You analyze inefficiencies already detected in a coding-agent session.

A deterministic analyzer has already identified the issue.
Your job is NOT to discover new issues.
Use only the supplied issue, evidence and context.

Never invent:
- tool calls;
- errors;
- token counts;
- timestamps;
- user interventions;
- causes not supported by evidence.

If the exact cause cannot be established, phrase it as a possible explanation
rather than a fact (for example: "this may indicate...", "a likely reason is...").

Give a concrete recommendation that could improve the next coding-agent session.

The AGENTS.md rule must:
- be concise (one or two sentences);
- be actionable;
- be standalone (understandable without this report);
- describe behavior the agent should follow in future sessions;
- be written in the imperative mood, without step numbers or session-specific details.

Write in English, in plain professional prose. No markdown, no bullet lists,
no headings inside field values.

Return ONLY a JSON object with exactly these string fields:
  "title"          - short human-readable name of the problem (max ~60 chars);
  "explanation"    - what concretely happened, based strictly on the evidence;
  "impact"         - why this is inefficient (extra tool calls, tokens, time,
                     lack of progress);
  "recommendation" - a concrete action for the next session;
  "agent_rule"     - one standalone rule ready to paste into AGENTS.md.

Do not add any other fields, comments or text outside the JSON object.
"""

# Used for structured output / JSON-schema mode when the provider supports it.
RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "explanation": {"type": "string"},
        "impact": {"type": "string"},
        "recommendation": {"type": "string"},
        "agent_rule": {"type": "string"},
    },
    "required": ["title", "explanation", "impact", "recommendation", "agent_rule"],
    "additionalProperties": False,
}


def build_user_prompt(issue: Issue) -> str:
    """Render one issue as the user message. Nothing else is sent."""
    payload = json.dumps(issue.to_prompt_dict(), ensure_ascii=False, indent=2)
    return (
        "A deterministic analyzer detected the following issue in a "
        "coding-agent session.\n\n"
        "Issue JSON:\n"
        f"{payload}\n\n"
        "Explain this issue and produce the AGENTS.md rule. "
        "Use only the facts present in the JSON above."
    )
