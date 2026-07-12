"""`tokenlens scan` — per-session table of raw token totals (Issue 1).

Output is RAW/UNCORRECTED: streaming duplicates are NOT deduplicated here,
so totals overcount. Issue 2 layers corrected accounting on top.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tokenlens.ingest.parser import Event, ScanResult, parse_dir, parse_timestamp
from tokenlens.render import fmt_duration, fmt_tokens, format_table


def _session_row(session_id: str, events: list[Event]) -> list[str]:
    ordered = sorted(events, key=lambda e: e.timestamp)
    first, last = parse_timestamp(ordered[0].timestamp), parse_timestamp(ordered[-1].timestamp)
    return [
        session_id,
        str(len(events)),
        fmt_tokens(sum(e.input_tokens for e in events)),
        fmt_tokens(sum(e.cache_creation_tokens for e in events)),
        fmt_tokens(sum(e.cache_read_tokens for e in events)),
        fmt_tokens(sum(e.output_tokens for e in events)),
        ",".join(sorted({e.model for e in events})),
        ",".join(sorted({e.version for e in events})),
        fmt_duration((last - first).total_seconds()),
    ]


def render_scan(result: ScanResult) -> str:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in result.events:
        by_session[event.session_id].append(event)

    sessions = sorted(by_session.items(), key=lambda kv: min(e.timestamp for e in kv[1]))
    headers = [
        "session",
        "events",
        "input",
        "cache_w",
        "cache_r",
        "output~",
        "models",
        "versions",
        "duration",
    ]
    rows = [_session_row(sid, events) for sid, events in sessions]

    lines = [
        "RAW/UNCORRECTED — streaming duplicates not deduplicated (Issue 2)",
        "",
        format_table(headers, rows) if rows else "(no usage-bearing events found)",
        "",
        f"files: {result.files_scanned}   lines: {result.lines_total}   "
        f"malformed (skipped): {result.malformed_lines}",
        f"events (raw): {len(result.events)}   sessions: {len(sessions)}",
        "~ output_tokens are streaming placeholders — treat as estimates",
    ]
    return "\n".join(lines)


def run(path: Path) -> int:
    if not path.is_dir():
        print(f"tokenlens scan: not a directory: {path}")
        return 1
    print(render_scan(parse_dir(path)))
    return 0
