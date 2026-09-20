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

Work out WHY it happened, not only what happened: what the agent did not know,
did not check or was not told. Typical causes: the project instructions do not
name the test/build command; the agent did not read the error output before
acting; a long-running command was run in the foreground; a permission or tool
was missing; the task statement was ambiguous.

Then give ONE concrete change for the next session and say where it belongs
("fix_kind"):
- "instruction": a rule for CLAUDE.md / AGENTS.md (the default);
- "skill": a multi-step procedure worth packaging as a reusable skill
  (for example "how to run and debug the tests in this repo");
- "tool": a tool, MCP server or CLI the agent should have had;
- "hook": an automatic check the harness should run (lint after edit, block a command);
- "settings": permissions, timeouts, background execution, model or effort.

Be specific to this session: name the actual command, file, tool or error text
from the evidence. A recommendation that would fit any project is a bad one.

The AGENTS.md rule must:
- be concise (one or two sentences);
- be actionable and specific (name the command or file when the evidence has it);
- be standalone (understandable without this report);
- be written in the imperative mood, without step numbers.

Write every field value in Russian, in plain professional prose; keep commands,
file names, tool names and error text verbatim. No markdown, no bullet lists,
no headings inside field values.

Return ONLY a JSON object with exactly these string fields:
  "title"          - short name of the problem (max ~60 chars);
  "explanation"    - what concretely happened, based strictly on the evidence;
  "cause"          - why it happened (hedged if the evidence does not settle it);
  "impact"         - what it cost: extra tool calls, tokens, money, time;
  "recommendation" - the concrete change for the next session;
  "fix_kind"       - one of: instruction, skill, tool, hook, settings;
  "agent_rule"     - one standalone rule ready to paste into CLAUDE.md / AGENTS.md.

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
        "cause": {"type": "string"},
        "fix_kind": {"type": "string", "enum": ["instruction", "skill", "tool", "hook", "settings"]},
    },
    "required": ["title", "explanation", "impact", "recommendation", "agent_rule", "cause", "fix_kind"],
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
        "Use only the facts present in the JSON above.\n\n"
        "Отвечай на русском языке: все значения полей JSON - по-русски, "
        "команды, имена файлов и тексты ошибок оставляй как есть."
    )
