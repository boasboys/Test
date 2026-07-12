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
from tokenlens.ingest.parser import Event, ScanResult, parse_dir
from tokenlens.pricing.engine import Snapshot
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


def render_triggers(result: ScanResult, snapshot: Snapshot) -> str:
    from decimal import Decimal

    from tokenlens.forensics.attribution import (
        INVESTIGATE_UNKNOWN_RATE,
        TRIGGERS,
        attribute_all,
        unknown_rate,
    )

    attributions = attribute_all(result, snapshot)
    rows: list[list[str]] = []
    for trigger in TRIGGERS:
        matching = [a for a in attributions if a.trigger == trigger]
        if not matching:
            continue
        total = sum((a.damage_usd for a in matching), Decimal(0))
        rows.append(
            [trigger, str(len(matching)), f"${total:.4f}", f"${total / len(matching):.4f}"]
        )

    rate = unknown_rate(attributions)
    lines = [
        f"Bust trigger attribution — snapshot {snapshot.snapshot_id!r}"
        + ("" if snapshot.verified else " (UNVERIFIED — human gate pending)"),
        "",
        format_table(["trigger", "busts", "damage", "avg"], rows)
        if rows
        else "(no bust events detected)",
        "",
        f"unknown rate: {rate:.0%}"
        + (
            "  !! above 40% — open an investigation issue (docs/issues/issue-05.md)"
            if rate > INVESTIGATE_UNKNOWN_RATE
            else ""
        ),
    ]
    return "\n".join(lines)


def run(
    path: Path,
    triggers: bool = False,
    pricing_dir: Path | None = None,
    snapshot_id: str | None = None,
) -> int:
    if not path.is_dir():
        print(f"tokenlens cache: not a directory: {path}")
        return 1
    result = parse_dir(path)
    print(render_cache(result.events))
    if triggers:
        from tokenlens.pricing.engine import (
            SnapshotError,
            UnknownModelError,
            latest_snapshot,
            load_snapshot,
        )

        pricing = pricing_dir if pricing_dir is not None else Path("pricing")
        try:
            snapshot = (
                load_snapshot(pricing / f"{snapshot_id}.yaml")
                if snapshot_id
                else latest_snapshot(pricing)
            )
            print()
            print(render_triggers(result, snapshot))
        except (SnapshotError, UnknownModelError) as exc:
            print(f"tokenlens cache: {exc}")
            return 1
    return 0
