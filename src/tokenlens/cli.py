"""tokenlens command-line entry point.

Commands land with their issues (see docs/issues/); the rest are stubs that
exit with status 2 and point at the issue file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tokenlens import __version__
from tokenlens.forensics import cache_cmd
from tokenlens.ingest import scan

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"

_PLANNED_COMMANDS: dict[str, str] = {
    "cost": "issue-03",
    "tasks": "issue-06",
    "reconcile": "issue-08",
    "audit": "issue-09",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tokenlens",
        description="Local-first analyzer for Claude Code spend.",
    )
    parser.add_argument("--version", action="version", version=f"tokenlens {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan", help="per-session table of raw token totals from JSONL transcripts"
    )
    scan_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_PROJECTS_DIR,
        help="directory of Claude Code JSONL transcripts (default: ~/.claude/projects)",
    )
    scan_parser.add_argument(
        "--fanout",
        action="store_true",
        help="also report sub-agent lineage and fan-out metrics per family",
    )

    cache_parser = subparsers.add_parser(
        "cache", help="per-session cache health, bust events, fleet histogram"
    )
    cache_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_PROJECTS_DIR,
        help="directory of Claude Code JSONL transcripts (default: ~/.claude/projects)",
    )

    for name, issue in _PLANNED_COMMANDS.items():
        subparsers.add_parser(name, help=f"not implemented yet (docs/issues/{issue}.md)")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "scan":
        return scan.run(args.path, fanout=args.fanout)
    if args.command == "cache":
        return cache_cmd.run(args.path)
    issue = _PLANNED_COMMANDS[args.command]
    print(
        f"tokenlens {args.command}: not implemented yet — lands with docs/issues/{issue}.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
