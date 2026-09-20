"""AGENTS.md / CLAUDE.md generation from issue explanations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from .schemas import IssueExplanation, severity_rank

__all__ = ["generate_agents_md", "save_agents_md", "SECTION_BY_ISSUE_TYPE"]

DEFAULT_TITLE = "Agent Rules"
EMPTY_BODY = "_No inefficiencies were detected in this session._"

# Very simple grouping: issue type -> section heading.
SECTION_BY_ISSUE_TYPE: dict[str, str] = {
    "repeated_tool_call": "Repository exploration",
    "tool_failure": "Tool usage",
    "retry": "Tool usage",
    "token_hotspot": "Context and token usage",
    "session_error": "Tool usage",
    "human_intervention": "Working with the user",
    "idle_period": "Progress and pacing",
    "reverted_edit": "Editing code",
}
FALLBACK_SECTION = "General"

# Order in which known sections appear; unknown ones follow alphabetically.
_SECTION_ORDER = [
    "Repository exploration",
    "Tool usage",
    "Editing code",
    "Context and token usage",
    "Working with the user",
    "Progress and pacing",
]


def _normalize_rule(rule: str) -> str:
    """Clean a single rule so it is ready to paste into a markdown list."""
    text = re.sub(r"\s+", " ", (rule or "").strip())
    text = text.lstrip("-*• ").strip()
    text = re.sub(r"^\d+[.)]\s*", "", text)
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text[0].upper() + text[1:]


def _dedup_key(rule: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", rule.casefold()).strip()


def _section_for(explanation: IssueExplanation) -> str:
    return SECTION_BY_ISSUE_TYPE.get(explanation.issue_type, FALLBACK_SECTION)


def _section_sort_key(section: str) -> tuple[int, str]:
    if section in _SECTION_ORDER:
        return (_SECTION_ORDER.index(section), "")
    if section == FALLBACK_SECTION:
        return (len(_SECTION_ORDER) + 1, "")
    return (len(_SECTION_ORDER), section.lower())


def generate_agents_md(
    explanations: Sequence[IssueExplanation] | Iterable[IssueExplanation] | None,
    *,
    title: str = DEFAULT_TITLE,
    group_by_section: bool = True,
) -> str:
    """Render rules as a markdown document ready to be saved as-is.

    Empty rules are dropped and duplicates are removed (case- and
    punctuation-insensitive), keeping the first, highest-severity occurrence.
    """
    items = list(explanations or [])
    # Highest severity first so that the surviving copy of a duplicate rule is
    # the one from the most severe issue; input order breaks ties.
    ordered = sorted(
        enumerate(items), key=lambda pair: (severity_rank(pair[1].severity), pair[0])
    )

    seen: set[str] = set()
    sections: dict[str, list[str]] = {}
    for _, explanation in ordered:
        rule = _normalize_rule(explanation.agent_rule)
        if not rule:
            continue
        key = _dedup_key(rule)
        if not key or key in seen:
            continue
        seen.add(key)
        section = _section_for(explanation) if group_by_section else FALLBACK_SECTION
        sections.setdefault(section, []).append(rule)

    lines: list[str] = [f"# {title}", ""]
    if not sections:
        lines.append(EMPTY_BODY)
        return "\n".join(lines) + "\n"

    if not group_by_section:
        for rule in next(iter(sections.values())):
            lines.append(f"- {rule}")
        return "\n".join(lines) + "\n"

    for section in sorted(sections, key=_section_sort_key):
        lines.append(f"## {section}")
        lines.append("")
        lines.extend(f"- {rule}" for rule in sections[section])
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def save_agents_md(
    explanations: Sequence[IssueExplanation] | Iterable[IssueExplanation] | None,
    path: Path | str,
    **kwargs,
) -> Path:
    """Write the generated document to ``path`` (UTF-8) and return the path."""
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate_agents_md(explanations, **kwargs), encoding="utf-8")
    return target
