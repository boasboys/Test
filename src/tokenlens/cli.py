"""tokenlens command-line entry point.

Issue 0 ships subcommand stubs only; each command lands with its issue
(see docs/issues/). Stubs exit with status 2 and point at the issue file.
"""

from __future__ import annotations

import argparse
import sys

from tokenlens import __version__

_PLANNED_COMMANDS: dict[str, str] = {
    "scan": "issue-01",
    "cost": "issue-03",
    "cache": "issue-04",
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
    for name, issue in _PLANNED_COMMANDS.items():
        subparsers.add_parser(name, help=f"not implemented yet (docs/issues/{issue}.md)")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    issue = _PLANNED_COMMANDS[args.command]
    print(
        f"tokenlens {args.command}: not implemented yet — lands with docs/issues/{issue}.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
