"""tokenlens command-line entry point.

Commands land with their issues (see docs/issues/); the rest are stubs that
exit with status 2 and point at the issue file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tokenlens import __version__
from tokenlens.classify import tasks_cmd
from tokenlens.forensics import cache_cmd
from tokenlens.ingest import scan
from tokenlens.pricing import cost_cmd
from tokenlens.reconcile import reconcile_cmd

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_PRICING_DIR = Path("pricing")

_PLANNED_COMMANDS: dict[str, str] = {
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

    cost_parser = subparsers.add_parser(
        "cost", help="per-session dollar costs from a dated pricing snapshot"
    )
    cost_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_PROJECTS_DIR,
        help="directory of Claude Code JSONL transcripts (default: ~/.claude/projects)",
    )
    cost_parser.add_argument(
        "--pricing-dir",
        type=Path,
        default=DEFAULT_PRICING_DIR,
        help="directory of dated pricing snapshots (default: ./pricing)",
    )
    cost_parser.add_argument(
        "--snapshot",
        help="snapshot ID to price with, e.g. 2026-07 (default: latest in pricing dir)",
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
    cache_parser.add_argument(
        "--triggers",
        action="store_true",
        help="attribute each bust to a trigger and price the damage (Issue 5)",
    )
    cache_parser.add_argument(
        "--pricing-dir",
        type=Path,
        default=DEFAULT_PRICING_DIR,
        help="directory of dated pricing snapshots (default: ./pricing)",
    )
    cache_parser.add_argument(
        "--snapshot",
        help="snapshot ID to price bust damage with (default: latest in pricing dir)",
    )

    tasks_parser = subparsers.add_parser(
        "tasks", help="spend by task type (conversation/exploration/coding/...)"
    )
    tasks_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_PROJECTS_DIR,
        help="directory of Claude Code JSONL transcripts (default: ~/.claude/projects)",
    )
    tasks_parser.add_argument(
        "--pricing-dir",
        type=Path,
        default=DEFAULT_PRICING_DIR,
        help="directory of dated pricing snapshots (default: ./pricing)",
    )
    tasks_parser.add_argument(
        "--snapshot",
        help="snapshot ID to price with (default: latest in pricing dir)",
    )

    reconcile_parser = subparsers.add_parser(
        "reconcile", help="tie JSONL-derived dollars out against the Admin Cost API"
    )
    reconcile_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_PROJECTS_DIR,
        help="directory of Claude Code JSONL transcripts (default: ~/.claude/projects)",
    )
    reconcile_parser.add_argument(
        "--pricing-dir",
        type=Path,
        default=DEFAULT_PRICING_DIR,
        help="directory of dated pricing snapshots (default: ./pricing)",
    )
    reconcile_parser.add_argument(
        "--snapshot",
        help="snapshot ID to price with (default: latest in pricing dir)",
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
        return cache_cmd.run(
            args.path,
            triggers=args.triggers,
            pricing_dir=args.pricing_dir,
            snapshot_id=args.snapshot,
        )
    if args.command == "cost":
        return cost_cmd.run(args.path, args.pricing_dir, args.snapshot)
    if args.command == "tasks":
        return tasks_cmd.run(args.path, args.pricing_dir, args.snapshot)
    if args.command == "reconcile":
        return reconcile_cmd.run(args.path, args.pricing_dir, args.snapshot)
    issue = _PLANNED_COMMANDS[args.command]
    print(
        f"tokenlens {args.command}: not implemented yet — lands with docs/issues/{issue}.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
