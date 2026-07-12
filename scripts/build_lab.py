#!/usr/bin/env python3
"""Build the insight lab: DuckDB over canonical events + the six queries.

`make lab` entry point (Issue 10). Rebuilds lab/events.duckdb from the
corpus, then runs every lab/queries/q*.sql and prints the results, ending
with the Week-1 go/no-go readout:

- >30% of sessions below 85% cache health  => the bust thesis has legs
- <5% of spend recoverable                 => pivot signal

Tables: events (corrected + category + $), sessions (health), busts
(attributed + priced), families (fan-out), divergence (empty until a
reconcile run is exported — Q3 reads it either way).
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tokenlens.classify.turns import classify_sessions  # noqa: E402
from tokenlens.forensics.attribution import attribute_all  # noqa: E402
from tokenlens.forensics.health import cache_health, detect_busts  # noqa: E402
from tokenlens.ingest.accounting import dedup_last_wins  # noqa: E402
from tokenlens.ingest.lineage import build_families, fan_out  # noqa: E402
from tokenlens.ingest.parser import Event, parse_dir  # noqa: E402
from tokenlens.pricing.engine import Snapshot, cost_event, latest_snapshot  # noqa: E402

SCHEMA = """
CREATE TABLE events (
    session_id TEXT, event_uuid TEXT, message_id TEXT, request_id TEXT,
    model TEXT, version TEXT, ts TEXT, is_sidechain BOOLEAN, agent_id TEXT,
    input_tokens BIGINT, cache_creation_tokens BIGINT, cache_creation_5m BIGINT,
    cache_creation_1h BIGINT, cache_read_tokens BIGINT, output_tokens BIGINT,
    service_tier TEXT, category TEXT,
    input_usd DECIMAL(18, 10), cache_write_usd DECIMAL(18, 10),
    cache_read_usd DECIMAL(18, 10), output_usd_est DECIMAL(18, 10),
    total_usd DECIMAL(18, 10), snapshot_id TEXT
);
CREATE TABLE sessions (
    session_id TEXT, events INTEGER, health DOUBLE, busts INTEGER
);
CREATE TABLE busts (
    session_id TEXT, turn INTEGER, message_id TEXT, kind TEXT,
    trigger TEXT, damage_usd DECIMAL(18, 10), snapshot_id TEXT
);
CREATE TABLE families (
    root_session TEXT, subagent_count INTEGER, family_tokens BIGINT,
    subagent_tokens BIGINT, subagent_share DOUBLE,
    fanout_multiplier DOUBLE, haiku_share DOUBLE
);
CREATE TABLE divergence (
    date TEXT, stream TEXT, jsonl_usd DECIMAL(18, 10), api_usd DECIMAL(18, 10),
    divergence DOUBLE, classification TEXT
);
"""


def build_db(corpus: Path, db_path: Path, snapshot: Snapshot) -> duckdb.DuckDBPyConnection:
    result = parse_dir(corpus)
    corrected = dedup_last_wins(result.events)
    categories, _ = classify_sessions(corrected)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # rebuilt artifact — always from scratch
    con = duckdb.connect(str(db_path))
    for statement in SCHEMA.strip().split(";"):
        if statement.strip():
            con.execute(statement)

    event_rows = []
    by_session: dict[str, list[Event]] = {}
    for event in corrected:
        by_session.setdefault(event.session_id, []).append(event)
        cost = cost_event(event, snapshot)
        event_rows.append(
            (
                event.session_id, event.event_uuid, event.message_id, event.request_id,
                event.model, event.version, event.timestamp, event.is_sidechain,
                event.agent_id, event.input_tokens, event.cache_creation_tokens,
                event.cache_creation_5m, event.cache_creation_1h,
                event.cache_read_tokens, event.output_tokens, event.service_tier,
                categories[event.event_uuid], cost.input_usd, cost.cache_write_usd,
                cost.cache_read_usd, cost.output_usd_estimated, cost.total_usd,
                cost.snapshot_id,
            )
        )
    if event_rows:
        con.executemany(
            f"INSERT INTO events VALUES ({', '.join('?' * 23)})", event_rows
        )

    session_rows = []
    for session_id, events in sorted(by_session.items()):
        score = cache_health(events)
        session_rows.append(
            (session_id, len(events), score, len(detect_busts(events)))
        )
    if session_rows:
        con.executemany("INSERT INTO sessions VALUES (?, ?, ?, ?)", session_rows)

    bust_rows = [
        (
            a.bust.session_id, a.bust.turn, a.bust.message_id, a.bust.kind,
            a.trigger, a.damage_usd, a.snapshot_id,
        )
        for a in attribute_all(result, snapshot)
    ]
    if bust_rows:
        con.executemany("INSERT INTO busts VALUES (?, ?, ?, ?, ?, ?, ?)", bust_rows)

    family_rows = [
        (
            f.root_session, f.subagent_count, f.family_tokens, f.subagent_tokens,
            f.subagent_share, f.fanout_multiplier, f.haiku_share,
        )
        for f in (fan_out(fam) for fam in build_families(result))
    ]
    if family_rows:
        con.executemany("INSERT INTO families VALUES (?, ?, ?, ?, ?, ?, ?)", family_rows)
    return con


def run_queries(con: duckdb.DuckDBPyConnection, queries_dir: Path) -> dict[str, list]:
    outputs: dict[str, list] = {}
    for sql_file in sorted(queries_dir.glob("q*.sql")):
        rows = con.execute(sql_file.read_text(encoding="utf-8")).fetchall()
        outputs[sql_file.stem] = rows
        print(f"\n== {sql_file.stem} ==")
        if rows:
            for row in rows:
                print("  " + " | ".join(str(cell) for cell in row))
        else:
            print("  (no rows)")
    return outputs


def go_no_go(con: duckdb.DuckDBPyConnection) -> tuple[float, float]:
    """Returns (share of sessions below 85% health, recoverable spend share)."""
    below, total = con.execute(
        "SELECT count(*) FILTER (health < 0.85), count(*) FROM sessions "
        "WHERE health IS NOT NULL"
    ).fetchone()
    below_share = (below / total) if total else 0.0
    damage = con.execute("SELECT coalesce(sum(damage_usd), 0) FROM busts").fetchone()[0]
    spend = con.execute("SELECT coalesce(sum(total_usd), 0) FROM events").fetchone()[0]
    recoverable = float(Decimal(damage) / Decimal(spend)) if spend else 0.0
    return below_share, recoverable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("lab/corpus/raw"))
    parser.add_argument("--db", type=Path, default=Path("lab/events.duckdb"))
    parser.add_argument("--queries", type=Path, default=Path("lab/queries"))
    parser.add_argument("--pricing-dir", type=Path, default=Path("pricing"))
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        print(f"corpus not found: {args.corpus} — run `make corpus` first", file=sys.stderr)
        return 1
    snapshot = latest_snapshot(args.pricing_dir)
    con = build_db(args.corpus, args.db, snapshot)
    print(f"built {args.db} (snapshot {snapshot.snapshot_id}"
          + ("" if snapshot.verified else ", UNVERIFIED") + ")")
    run_queries(con, args.queries)

    below_share, recoverable = go_no_go(con)
    print("\n== go/no-go ==")
    print(
        f"  sessions below 85% health: {below_share:.0%} "
        + ("=> bust thesis has legs" if below_share > 0.30 else "(threshold: >30%)")
    )
    print(
        f"  recoverable spend share: {recoverable:.1%} "
        + ("=> PIVOT SIGNAL" if recoverable < 0.05 else "(threshold: <5%)")
    )
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
