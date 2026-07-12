"""`tokenlens cache` — per-session cache health + fleet histogram (Issue 4)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tokenlens.forensics.health import (
    EXCELLENT_THRESHOLD,
    HEALTHY_THRESHOLD,
    cache_health,
    detect_busts,
)
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, parse_dir
from tokenlens.render import format_table

# Histogram buckets aligned to the reference thresholds so the 85% / 92%
# lines fall exactly on bucket boundaries.
_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.50, "  0-50%"),
    (0.50, 0.70, " 50-70%"),
    (0.70, HEALTHY_THRESHOLD, " 70-85%"),
    (HEALTHY_THRESHOLD, EXCELLENT_THRESHOLD, " 85-92%"),
    (EXCELLENT_THRESHOLD, 1.01, "92-100%"),
)


def _histogram(scores: list[float]) -> str:
    lines = ["fleet cache-health histogram"]
    for low, high, label in _BUCKETS:
        count = sum(1 for s in scores if low <= s < high)
        lines.append(f"{label}  {'#' * count}{' ' if count else ''}{count}")
        if high == HEALTHY_THRESHOLD:
            lines.append("-------- 85% healthy reference --------")
        if high == EXCELLENT_THRESHOLD:
            lines.append("-------- 92% excellent reference ------")
    return "\n".join(lines)


def render_cache(events: list[Event]) -> str:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in dedup_last_wins(events):
        by_session[event.session_id].append(event)

    rows: list[list[str]] = []
    scores: list[float] = []
    total_busts = 0
    sessions = sorted(by_session.items(), key=lambda kv: min(e.timestamp for e in kv[1]))
    for session_id, session_events in sessions:
        score = cache_health(session_events)
        busts = detect_busts(session_events)
        total_busts += len(busts)
        if score is not None:
            scores.append(score)
        bust_summary = ",".join(f"t{b.turn}:{b.kind}" for b in busts) or "-"
        rows.append(
            [
                session_id,
                str(len(session_events)),
                f"{score:.1%}" if score is not None else "n/a",
                bust_summary,
            ]
        )

    below = sum(1 for s in scores if s < HEALTHY_THRESHOLD)
    lines = [
        "Cache forensics — corrected events (last-wins dedup)",
        "",
        format_table(["session", "turns", "health", "busts"], rows)
        if rows
        else "(no usage-bearing events found)",
        "",
        _histogram(scores),
        "",
        f"sessions: {len(rows)}   bust events: {total_busts}   "
        f"below {HEALTHY_THRESHOLD:.0%} health: {below}/{len(scores)}",
        "health = cache_read / (cache_read + cache_creation + input)",
    ]
    return "\n".join(lines)


def run(path: Path) -> int:
    if not path.is_dir():
        print(f"tokenlens cache: not a directory: {path}")
        return 1
    print(render_cache(parse_dir(path).events))
    return 0
