"""Ready-to-use files built from the explanations.

The case for them: a recommendation nobody has to retype is one that gets
applied. Everything here is rendered by code from fields the LLM already
produced, and every line keeps a pointer to the steps it came from.
"""

from __future__ import annotations

import re
from typing import Sequence

from pydantic import BaseModel

from .agents_md import _dedup_key, _is_duplicate, _normalize_rule, generate_agents_md
from .schemas import IssueExplanation, severity_rank

__all__ = ["Artifact", "build_artifacts"]

_KIND_TITLES = {
    "instruction": "Правила в CLAUDE.md / AGENTS.md",
    "skill": "Скиллы",
    "tool": "Инструменты и MCP",
    "hook": "Хуки",
    "settings": "Настройки",
}
_PROCEDURAL = ("retry", "tool_failure", "human_intervention", "repeated_tool_call", "reverted_edit")
_TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     "a b v g d e e zh z i y k l m n o p r s t u f h c ch sh sch _ y _ e yu ya".split()))


class Artifact(BaseModel):
    """One file the user can drop into the project as-is."""

    path: str
    description: str
    content: str


def build_artifacts(explanations: Sequence[IssueExplanation], session_name: str = "") -> list[Artifact]:
    ordered = sorted(explanations, key=lambda item: severity_rank(item.severity))
    if not ordered:
        return []
    artifacts = [
        Artifact(path="AGENTS.md", description="Правила для агента, сгруппированные по темам.",
                 content=generate_agents_md(ordered)),
        Artifact(path="CLAUDE.md.append.md",
                 description="Блок для вставки в конец CLAUDE.md: правило + из каких шагов оно выведено.",
                 content=_claude_md_block(ordered, session_name)),
    ]
    skills = [item for item in ordered if item.fix_kind == "skill"]
    if not skills:
        # Models rarely pick "skill" on their own. The most significant procedural
        # problem (how to run, retry, verify) is still worth a reusable draft.
        skills = [item for item in ordered if item.issue_type in _PROCEDURAL][:1]
    artifacts.extend(_skill(item) for item in skills)
    artifacts.append(Artifact(path="NEXT_SESSION.md",
                              description="Чек-лист перед следующей сессией: что поменять и где.",
                              content=_checklist(ordered)))
    return artifacts


def _steps(item: IssueExplanation) -> str:
    return ", ".join(str(step) for step in item.steps) or "-"


def _claude_md_block(items: Sequence[IssueExplanation], session_name: str) -> str:
    lines = [f"## Правила из разбора сессии{f' {session_name}' if session_name else ''}", ""]
    seen: list[str] = []
    for item in items:
        rule = _normalize_rule(item.agent_rule)
        key = _dedup_key(rule)
        if not rule or not key or _is_duplicate(key, seen):
            continue
        seen.append(key)
        lines.append(f"- {rule}")
        lines.append(f"  <!-- {item.issue_type}, шаги {_steps(item)}: {item.title} -->")
    return "\n".join(lines) + "\n"


def _slug(title: str) -> str:
    text = "".join(_TRANSLIT.get(char, char) for char in title.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or "session-skill"


def _skill(item: IssueExplanation) -> Artifact:
    slug = _slug(item.title)
    description = re.sub(r"\s+", " ", item.recommendation)[:200]
    content = (
        f"---\nname: {slug}\ndescription: {description}\n---\n\n"
        f"# {item.title}\n\n"
        f"## Когда применять\n\n{item.explanation}\n\n"
        f"## Почему это нужно\n\n{item.cause or item.impact}\n\n"
        f"## Что делать\n\n{item.recommendation}\n\n"
        f"## Правило\n\n{_normalize_rule(item.agent_rule)}\n\n"
        f"<!-- Черновик из разбора сессии: {item.issue_type}, шаги {_steps(item)}. "
        f"Допишите точные команды проекта. -->\n"
    )
    return Artifact(path=f".claude/skills/{slug}/SKILL.md",
                    description=f"Черновик скилла: {item.title}", content=content)


def _checklist(items: Sequence[IssueExplanation]) -> str:
    lines = ["# Что поменять к следующей сессии", ""]
    for kind, heading in _KIND_TITLES.items():
        group = [item for item in items if item.fix_kind == kind]
        if not group:
            continue
        lines += [f"## {heading}", ""]
        for item in group:
            lines.append(f"- [ ] **{item.title}** ({item.severity}, шаги {_steps(item)}) - {item.recommendation}")
            if item.cause:
                lines.append(f"  - Причина: {item.cause}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
