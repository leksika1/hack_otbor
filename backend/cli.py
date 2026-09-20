"""Command-line entry point for checking a real log without the API.

    python -m backend.cli path/to/rollout.jsonl
    python -m backend.cli session.jsonl --json --agents-md AGENTS.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.core.logging import setup_logging
from backend.parser import LOG_FORMATS
from backend.services import analyze_session_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a coding-agent session log")
    parser.add_argument("log", type=Path, help="path to a .jsonl session log")
    parser.add_argument("--format", choices=LOG_FORMATS, default="auto", help="log format (default: auto)")
    parser.add_argument("--max-issues", type=int, default=None, help="issues sent to the LLM")
    parser.add_argument("--no-llm", action="store_true", help="deterministic findings only")
    parser.add_argument("--agents-md", type=Path, default=None, help="write the generated rules here")
    parser.add_argument("--json", action="store_true", help="print the raw JSON report")
    parser.add_argument("--log-level", default="WARNING", help="logging level (default: WARNING)")
    args = parser.parse_args(argv)

    setup_logging(args.log_level)
    if not args.log.is_file():
        print(f"No such file: {args.log}", file=sys.stderr)
        return 2

    report = analyze_session_sync(
        args.log,
        file_name=args.log.name,
        log_format=args.format,
        max_issues=0 if args.no_llm else args.max_issues,
    )

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        _print_human(report)

    if args.agents_md:
        args.agents_md.write_text(report.agents_md, encoding="utf-8")
        print(f"\nwritten: {args.agents_md}")
    return 0


def _print_human(report) -> None:
    summary = report.summary
    print(f"{summary.file_name or 'log'}  format={summary.log_format}  steps={summary.steps}  "
          f"tokens={summary.tokens}  findings={summary.issues_total}  "
          f"explained={summary.issues_explained}  provider={report.provider}")
    for warning in report.warnings[:10]:
        print(f"  ! {warning}")

    print("\n--- findings ---")
    for finding in report.findings[:40]:
        print(f"[{finding.severity:6}] {finding.type:20} steps={finding.steps} {finding.message}")

    print("\n--- explanations ---")
    for item in report.explanations:
        print(f"\n## {item.title} ({item.severity}, steps {item.steps})")
        print(item.explanation)
        print(item.impact)
        print(f"-> {item.recommendation}")

    print("\n--- AGENTS.md ---")
    print(report.agents_md)


if __name__ == "__main__":
    sys.exit(main())
