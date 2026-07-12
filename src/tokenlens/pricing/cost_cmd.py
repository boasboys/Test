"""`tokenlens cost` — per-session dollar costs from a dated snapshot (Issue 3)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, parse_dir
from tokenlens.pricing.engine import (
    EventCost,
    Snapshot,
    SnapshotError,
    UnknownModelError,
    cost_event,
    latest_snapshot,
    load_snapshot,
)
from tokenlens.render import format_table


def _usd(value: Decimal) -> str:
    return f"${value:.4f}"


def render_cost(events: list[Event], snapshot: Snapshot) -> str:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in dedup_last_wins(events):
        by_session[event.session_id].append(event)

    rows: list[list[str]] = []
    grand_total = Decimal(0)
    sessions = sorted(by_session.items(), key=lambda kv: min(e.timestamp for e in kv[1]))
    for session_id, session_events in sessions:
        costs: list[EventCost] = [cost_event(e, snapshot) for e in session_events]
        total = sum((c.total_usd for c in costs), Decimal(0))
        grand_total += total
        rows.append(
            [
                session_id,
                _usd(sum((c.input_usd for c in costs), Decimal(0))),
                _usd(sum((c.cache_write_usd for c in costs), Decimal(0))),
                _usd(sum((c.cache_read_usd for c in costs), Decimal(0))),
                _usd(sum((c.output_usd_estimated for c in costs), Decimal(0))),
                _usd(total),
            ]
        )

    lines = [
        f"Cost per session — pricing snapshot {snapshot.snapshot_id!r}"
        + ("" if snapshot.verified else " (UNVERIFIED — human gate pending)"),
        "",
        format_table(
            ["session", "input", "cache_w", "cache_r", "output~", "total"], rows
        )
        if rows
        else "(no usage-bearing events found)",
        "",
        f"grand total: {_usd(grand_total)}   snapshot: {snapshot.snapshot_id}",
        "~ output cost is estimated (output_tokens are streaming placeholders)",
    ]
    return "\n".join(lines)


def run(path: Path, pricing_dir: Path, snapshot_id: str | None = None) -> int:
    if not path.is_dir():
        print(f"tokenlens cost: not a directory: {path}")
        return 1
    try:
        snapshot = (
            load_snapshot(pricing_dir / f"{snapshot_id}.yaml")
            if snapshot_id
            else latest_snapshot(pricing_dir)
        )
        print(render_cost(parse_dir(path).events, snapshot))
    except (SnapshotError, UnknownModelError) as exc:
        print(f"tokenlens cost: {exc}")
        return 1
    return 0
