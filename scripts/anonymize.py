#!/usr/bin/env python3
"""Snapshot Claude Code JSONL transcripts into the lab corpus, anonymized.

Strips cwd paths, git branches, and all message content; keeps only structure
+ usage metadata + timestamps + model/version fields (Issue 0). Malformed
lines are preserved as a content-free non-JSON marker so downstream parsers
stay honest about the skip path (CLAUDE.md invariant 6).

Usage:
    python3 scripts/anonymize.py [--source ~/.claude/projects] [--dest lab/corpus/raw]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

MALFORMED_MARKER = "[tokenlens: malformed line redacted]"

# Structural / metadata fields kept verbatim at the top level of each entry.
ALLOWED_TOP_LEVEL = {
    "type",
    "uuid",
    "parentUuid",
    "sessionId",
    "timestamp",
    "version",
    "requestId",
    "isSidechain",
    "isMeta",
    "userType",
    "agentId",
    "parentToolUseId",
}

# Fields kept verbatim inside `message`. `usage` is the whole point.
ALLOWED_MESSAGE = {"id", "type", "role", "model", "stop_reason", "usage"}


def _summarize_content(content: Any) -> Any:
    """Replace message content with a structure-only summary (no text)."""
    if isinstance(content, str):
        return [{"type": "text"}]
    if not isinstance(content, list):
        return []
    summary: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        entry: dict[str, Any] = {"type": block.get("type", "unknown")}
        # Tool identity is structure, not content — needed for task-type
        # classification (Issue 6) and sub-agent lineage (Issue 7).
        if block.get("type") in ("tool_use", "server_tool_use"):
            entry["id"] = block.get("id")
            entry["name"] = block.get("name")
        if block.get("type") == "tool_result":
            entry["tool_use_id"] = block.get("tool_use_id")
        summary.append(entry)
    return summary


def anonymize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep structure + usage metadata; drop paths, branches, and content."""
    out: dict[str, Any] = {k: v for k, v in entry.items() if k in ALLOWED_TOP_LEVEL}
    message = entry.get("message")
    if isinstance(message, dict):
        kept = {k: v for k, v in message.items() if k in ALLOWED_MESSAGE}
        if "content" in message:
            kept["content"] = _summarize_content(message["content"])
        out["message"] = kept
    return out


def _hash_name(name: str) -> str:
    """Project dir names embed cwd paths — replace with a stable hash."""
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def snapshot(source: Path, dest: Path) -> dict[str, Any]:
    """Anonymize every *.jsonl under source into dest; return a manifest."""
    files = sorted(source.rglob("*.jsonl"))
    manifest: dict[str, Any] = {"source_files": len(files), "files": {}}
    for path in files:
        rel = path.relative_to(source)
        anon_rel = Path(*[_hash_name(p) for p in rel.parts[:-1]], rel.name)
        out_path = dest / anon_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines_out: list[str] = []
        malformed = 0
        with path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    lines_out.append(MALFORMED_MARKER)
                    continue
                if not isinstance(entry, dict):
                    malformed += 1
                    lines_out.append(MALFORMED_MARKER)
                    continue
                lines_out.append(json.dumps(anonymize_entry(entry), sort_keys=True))
        out_path.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
        manifest["files"][str(anon_rel)] = {"lines": len(lines_out), "malformed": malformed}
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="directory containing Claude Code JSONL transcripts",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("lab/corpus/raw"),
        help="corpus destination (gitignored; append-only — re-snapshot, never edit)",
    )
    args = parser.parse_args(argv)

    if not args.source.is_dir():
        print(f"source not found: {args.source} — nothing to snapshot", file=sys.stderr)
        return 1
    args.dest.mkdir(parents=True, exist_ok=True)
    manifest = snapshot(args.source, args.dest)
    total = sum(f["lines"] for f in manifest["files"].values())
    bad = sum(f["malformed"] for f in manifest["files"].values())
    print(f"snapshotted {manifest['source_files']} files, {total} lines ({bad} malformed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
