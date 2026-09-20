"""Manual check against a real log file.

    python -m backend.cli path/to/rollout.jsonl
    python -m backend.cli rollout.jsonl --json
    python -m backend.cli rollout.jsonl --agents-md AGENTS.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.pipeline import analyze_session_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a coding-agent session log")
    parser.add_argument("log", type=Path, help="path to a .jsonl session log")
    parser.add_argument("--max-issues", type=int, default=None, help="issues sent to the LLM")
    parser.add_argument("--no-llm", action="store_true", help="deterministic findings only")
    parser.add_argument("--agents-md", type=Path, default=None, help="write AGENTS.md here")
    parser.add_argument("--json", action="store_true", help="print the raw JSON response")
    args = parser.parse_args(argv)

    if not args.log.is_file():
        print(f"No such file: {args.log}", file=sys.stderr)
        return 2

    result = analyze_session_sync(
        args.log, max_issues=0 if args.no_llm else args.max_issues
    )

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        summary = result.summary
        print(f"steps={summary.steps} tokens={summary.tokens} findings={summary.issues_total} "
              f"explained={summary.issues_explained} provider={result.provider}")
        for warning in result.warnings[:10]:
            print(f"  ! {warning}")
        print("\n--- findings ---")
        for finding in result.findings[:40]:
            print(f"[{finding.severity:6}] {finding.type:20} steps={finding.steps} {finding.message}")
        print("\n--- explanations ---")
        for item in result.explanations:
            print(f"\n## {item.title} ({item.severity}, steps {item.steps})")
            print(f"{item.explanation}\n{item.impact}\n-> {item.recommendation}")
        print("\n--- AGENTS.md ---")
        print(result.agents_md)

    if args.agents_md:
        args.agents_md.write_text(result.agents_md, encoding="utf-8")
        print(f"written: {args.agents_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
