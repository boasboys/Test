"""`tokenlens tasks` — spend by task type, one-shot rates (Issue 6)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tokenlens.classify.turns import CATEGORIES, classify_sessions
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, parse_dir
from tokenlens.pricing.engine import (
    Snapshot,
    SnapshotError,
    UnknownModelError,
    cost_event,
    latest_snapshot,
    load_snapshot,
)
from tokenlens.render import format_table

# Published benchmarks to compare a corpus against (docs/issues/issue-06.md).
CONVERSATION_BENCHMARK = "25-56%"
EXPLORATION_BENCHMARK = "~47%"


def render_tasks(events: list[Event], snapshot: Snapshot) -> str:
    corrected = dedup_last_wins(events)
    categories, stats = classify_sessions(corrected)

    spend: dict[str, Decimal] = {c: Decimal(0) for c in CATEGORIES}
    for event in corrected:
        spend[categories[event.event_uuid]] += cost_event(event, snapshot).total_usd

    total_turns = sum(s.turns for s in stats.values())
    total_spend = sum(spend.values(), Decimal(0))

    rows: list[list[str]] = []
    for category in CATEGORIES:
        s = stats[category]
        if s.turns == 0:
            continue
        share = s.turns / total_turns
        spend_share = (spend[category] / total_spend) if total_spend else Decimal(0)
        one_shot = s.one_shot_rate
        rows.append(
            [
                category,
                str(s.turns),
                f"{share:.1%}",
                f"${spend[category]:.4f}",
                f"{spend_share:.1%}",
                f"{one_shot:.0%}" if one_shot is not None else "n/a",
            ]
        )

    def share_of(category: str) -> float:
        return stats[category].turns / total_turns if total_turns else 0.0

    lines = [
        f"Task-type breakdown — snapshot {snapshot.snapshot_id!r}"
        + ("" if snapshot.verified else " (UNVERIFIED — human gate pending)"),
        "",
        format_table(
            ["category", "turns", "share", "spend", "spend share", "one-shot"], rows
        )
        if rows
        else "(no usage-bearing events found)",
        "",
        f"turns: {total_turns}   classified spend: ${total_spend:.4f}   "
        f"snapshot: {snapshot.snapshot_id}",
        f"conversation: {share_of('conversation'):.1%} (benchmark {CONVERSATION_BENCHMARK})   "
        f"exploration: {share_of('exploration'):.1%} (benchmark {EXPLORATION_BENCHMARK})",
    ]
    return "\n".join(lines)


def run(path: Path, pricing_dir: Path, snapshot_id: str | None = None) -> int:
    if not path.is_dir():
        print(f"tokenlens tasks: not a directory: {path}")
        return 1
    try:
        snapshot = (
            load_snapshot(pricing_dir / f"{snapshot_id}.yaml")
            if snapshot_id
            else latest_snapshot(pricing_dir)
        )
        print(render_tasks(parse_dir(path).events, snapshot))
    except (SnapshotError, UnknownModelError) as exc:
        print(f"tokenlens tasks: {exc}")
        return 1
    return 0
