"""Issue 10 acceptance tests: `make lab` produces all six query outputs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import build_lab  # noqa: E402
from tokenlens.pricing.engine import load_snapshot  # noqa: E402

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
QUERIES = Path(__file__).parent.parent / "lab" / "queries"
PRICING = Path(__file__).parent.parent / "pricing"


@pytest.fixture(scope="module")
def lab_con(tmp_path_factory):
    snapshot = load_snapshot(PRICING / "2026-07.yaml")
    db = tmp_path_factory.mktemp("lab") / "events.duckdb"
    con = build_lab.build_db(GOLDEN, db, snapshot)
    yield con
    con.close()


def test_all_six_queries_exist_and_run(lab_con, capsys):
    """Acceptance: make lab produces all six query outputs from the corpus."""
    outputs = build_lab.run_queries(lab_con, QUERIES)
    assert sorted(outputs) == [
        "q1_cache_health",
        "q2_bust_triggers",
        "q3_divergence",
        "q4_task_spend",
        "q5_fanout",
        "q6_recoverable",
    ]
    out = capsys.readouterr().out
    for name in outputs:
        assert f"== {name} ==" in out


def test_events_table_holds_corrected_events(lab_con):
    (count,) = lab_con.execute("SELECT count(*) FROM events").fetchone()
    assert count == 20  # 23 raw -> 20 corrected on the golden corpus
    (snapshot_ids,) = lab_con.execute(
        "SELECT count(DISTINCT snapshot_id) FROM events"
    ).fetchone()
    assert snapshot_ids == 1  # every $ row carries the snapshot


def test_q1_buckets_cover_all_sessions(lab_con):
    rows = lab_con.execute((QUERIES / "q1_cache_health.sql").read_text()).fetchall()
    assert sum(sessions for _, sessions, _ in rows) == 6
    assert sum(share for _, _, share in rows) == pytest.approx(1.0, abs=0.01)


def test_q2_and_q6_expose_bust_damage(lab_con):
    triggers = lab_con.execute((QUERIES / "q2_bust_triggers.sql").read_text()).fetchall()
    assert [row[0] for row in triggers] == ["model_change", "version_change"]
    recoverable = lab_con.execute((QUERIES / "q6_recoverable.sql").read_text()).fetchall()
    assert float(recoverable[0][1]) == pytest.approx(0.2571)
    # Ranked descending by recoverable $.
    values = [float(row[1]) for row in recoverable]
    assert values == sorted(values, reverse=True)


def test_q4_spend_shares_sum_to_one(lab_con):
    rows = lab_con.execute((QUERIES / "q4_task_spend.sql").read_text()).fetchall()
    assert sum(float(share) for *_, share in rows) == pytest.approx(1.0, abs=0.01)


def test_q5_fanout_distribution(lab_con):
    rows = lab_con.execute((QUERIES / "q5_fanout.sql").read_text()).fetchall()
    by_count = {row[0]: row for row in rows}
    assert by_count[1][1] == 1  # exactly one family spawned a sub-agent
    assert float(by_count[1][2]) == pytest.approx(1.567, abs=0.001)


def test_go_no_go_thresholds(lab_con):
    below_share, recoverable = build_lab.go_no_go(lab_con)
    # Synthetic golden sessions are short: all below 85% -> thesis has legs.
    assert below_share == 1.0
    # And bust damage is a large share of this tiny corpus: no pivot signal.
    assert recoverable > 0.05


def test_main_end_to_end(tmp_path, capsys):
    db = tmp_path / "events.duckdb"
    code = build_lab.main(
        [
            "--corpus",
            str(GOLDEN),
            "--db",
            str(db),
            "--queries",
            str(QUERIES),
            "--pricing-dir",
            str(PRICING),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert db.exists()
    assert "== go/no-go ==" in out
    assert "bust thesis has legs" in out


def test_missing_corpus_fails_cleanly(tmp_path, capsys):
    code = build_lab.main(["--corpus", str(tmp_path / "nope"), "--db", str(tmp_path / "x.db")])
    assert code == 1
    assert "make corpus" in capsys.readouterr().err
