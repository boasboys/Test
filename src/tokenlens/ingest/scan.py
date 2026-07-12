"""`tokenlens scan` — per-session table of token totals (Issues 1, 2).

Per-session numbers are CORRECTED: streaming duplicates collapsed by
last-wins dedup on (message_id, request_id) — CLAUDE.md invariant 5. Raw
(uncorrected) counts are kept alongside for comparison, and the corpus-wide
dedup rate is reported.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tokenlens.ingest.accounting import dedup_last_wins, dedup_rate, stream_totals
from tokenlens.ingest.parser import STREAMS, Event, ScanResult, parse_dir, parse_timestamp
from tokenlens.render import fmt_duration, fmt_tokens, format_table


def _session_row(session_id: str, raw: list[Event], corrected: list[Event]) -> list[str]:
    ordered = sorted(raw, key=lambda e: e.timestamp)
    first, last = parse_timestamp(ordered[0].timestamp), parse_timestamp(ordered[-1].timestamp)
    totals = stream_totals(corrected)
    return [
        session_id,
        f"{len(raw)}>{len(corrected)}",
        fmt_tokens(totals["input_tokens"]),
        fmt_tokens(totals["cache_creation_tokens"]),
        fmt_tokens(totals["cache_read_tokens"]),
        fmt_tokens(totals["output_tokens"]),
        ",".join(sorted({e.model for e in corrected})),
        ",".join(sorted({e.version for e in corrected})),
        fmt_duration((last - first).total_seconds()),
    ]


def render_scan(result: ScanResult) -> str:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in result.events:
        by_session[event.session_id].append(event)

    sessions = sorted(by_session.items(), key=lambda kv: min(e.timestamp for e in kv[1]))
    headers = [
        "session",
        "raw>cor",
        "input",
        "cache_w",
        "cache_r",
        "output~",
        "models",
        "versions",
        "duration",
    ]
    rows = [_session_row(sid, events, dedup_last_wins(events)) for sid, events in sessions]

    corrected_all = dedup_last_wins(result.events)
    raw_totals = stream_totals(result.events)
    corrected_totals = stream_totals(corrected_all)
    rate = dedup_rate(len(result.events), len(corrected_all))

    totals_table = format_table(
        ["corpus totals", "input", "cache_w", "cache_r", "output~"],
        [
            ["raw (uncorrected)"] + [fmt_tokens(raw_totals[s]) for s in STREAMS],
            ["corrected (dedup)"] + [fmt_tokens(corrected_totals[s]) for s in STREAMS],
        ],
    )

    lines = [
        "CORRECTED token accounting — last-wins dedup by (message_id, request_id)",
        "",
        format_table(headers, rows) if rows else "(no usage-bearing events found)",
        "",
        totals_table,
        "",
        f"files: {result.files_scanned}   lines: {result.lines_total}   "
        f"malformed (skipped): {result.malformed_lines}",
        f"events: {len(result.events)} raw > {len(corrected_all)} corrected   "
        f"dedup rate: {rate:.1%}",
        "~ output_tokens are streaming placeholders — treat as estimates",
    ]
    return "\n".join(lines)


def run(path: Path) -> int:
    if not path.is_dir():
        print(f"tokenlens scan: not a directory: {path}")
        return 1
    print(render_scan(parse_dir(path)))
    return 0
