"""`tokenlens reconcile` — daily tie-out against the Admin Cost API (Issue 8)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import parse_dir
from tokenlens.pricing.engine import (
    Snapshot,
    SnapshotError,
    UnknownModelError,
    latest_snapshot,
    load_snapshot,
)
from tokenlens.reconcile import api_client
from tokenlens.reconcile.tieout import (
    RECONCILABLE_STREAMS,
    TOLERANCE,
    LedgerEntry,
    jsonl_daily_dollars,
    normalize_api_buckets,
    tie_out,
)
from tokenlens.render import format_table


def render_ledger(ledger: list[LedgerEntry], snapshot: Snapshot) -> str:
    rows = [
        [
            entry.date,
            entry.stream,
            f"${entry.jsonl_usd:.4f}",
            f"${entry.api_usd:.4f}",
            f"{entry.divergence:+.1%}" if entry.divergence is not None else "n/a",
            entry.classification,
        ]
        for entry in ledger
    ]

    lines = [
        f"Reconciliation ledger — snapshot {snapshot.snapshot_id!r}"
        + ("" if snapshot.verified else " (UNVERIFIED — human gate pending)"),
        "",
        format_table(["date", "stream", "jsonl", "api", "div", "classification"], rows)
        if rows
        else "(nothing to reconcile)",
        "",
    ]
    for stream in RECONCILABLE_STREAMS:
        entries = [e for e in ledger if e.stream == stream]
        jsonl_total = sum((e.jsonl_usd for e in entries), Decimal(0))
        api_total = sum((e.api_usd for e in entries), Decimal(0))
        overall = (jsonl_total - api_total) / api_total if api_total else None
        status = (
            "OK"
            if overall is not None and abs(overall) <= TOLERANCE
            else "INVESTIGATE"
        )
        lines.append(
            f"{stream}: jsonl ${jsonl_total:.4f} vs api ${api_total:.4f}"
            + (f"   {overall:+.1%} [{status}]" if overall is not None else "   [no api data]")
        )
    lines.append(f"target: within {TOLERANCE:.0%} per stream over the window")
    lines.append("output stream is estimated only — the API is ground truth for total cost")
    return "\n".join(lines)


def run(path: Path, pricing_dir: Path, snapshot_id: str | None = None) -> int:
    if not path.is_dir():
        print(f"tokenlens reconcile: not a directory: {path}")
        return 1
    try:
        snapshot = (
            load_snapshot(pricing_dir / f"{snapshot_id}.yaml")
            if snapshot_id
            else latest_snapshot(pricing_dir)
        )
        events = dedup_last_wins(parse_dir(path).events)
        if not events:
            print("tokenlens reconcile: no usage-bearing events found")
            return 1
        jsonl_daily = jsonl_daily_dollars(events, snapshot)

        # UTC-aligned window covering every day the JSONL touches.
        dates = sorted({date for date, _ in jsonl_daily})
        starting_at = f"{dates[0]}T00:00:00Z"
        ending_at = f"{dates[-1]}T23:59:59Z"
        buckets = api_client.fetch_cost_buckets(starting_at, ending_at)
        ledger = tie_out(jsonl_daily, normalize_api_buckets(buckets))
        print(render_ledger(ledger, snapshot))
    except api_client.MissingAdminKeyError as exc:
        print(f"tokenlens reconcile: {exc}")
        return 1
    except (SnapshotError, UnknownModelError, api_client.ApiError, ValueError) as exc:
        print(f"tokenlens reconcile: {exc}")
        return 1
    return 0
