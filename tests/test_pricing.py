"""Issue 3 acceptance tests: pricing engine + tokenlens cost.

The ten hand-computed cases below are the human-gate checklist from
docs/issues/issue-03.md — each expected value was computed by hand from the
2026-07 snapshot rates and must be re-verified by a human alongside the
snapshot itself.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.ingest.parser import Event, parse_dir
from tokenlens.pricing.engine import (
    SnapshotError,
    UnknownModelError,
    cost_event,
    latest_snapshot,
    load_snapshot,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
PRICING = Path(__file__).parent.parent / "pricing"

SONNET4 = "claude-sonnet-4-20250514"  # $3 in / $15 out per MTok in 2026-07
OPUS4 = "claude-opus-4-20250514"  # $15 in / $75 out
HAIKU = "claude-haiku-4-5-20251001"  # $1 in / $5 out


def make_event(
    model: str = SONNET4,
    inp: int = 0,
    cc_5m: int = 0,
    cc_1h: int = 0,
    cr: int = 0,
    out: int = 0,
    service_tier: str = "standard",
) -> Event:
    return Event(
        session_id="s",
        event_uuid="u",
        parent_uuid=None,
        is_sidechain=False,
        agent_id=None,
        message_id="m",
        request_id="r",
        model=model,
        version="1.0.44",
        timestamp="2026-07-01T10:00:00.000Z",
        input_tokens=inp,
        cache_creation_tokens=cc_5m + cc_1h,
        cache_creation_5m=cc_5m,
        cache_creation_1h=cc_1h,
        cache_read_tokens=cr,
        output_tokens=out,
        service_tier=service_tier,
        content_types=("text",),
        tool_names=(),
        tool_use_ids=(),
        source_file="synthetic",
    )


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(PRICING / "2026-07.yaml")


# ---- the 10 hand-computed cases (HUMAN GATE: verify each by hand) ----------
# (name, event, expected_total_usd)
HAND_COMPUTED = [
    # 1. Plain input, sonnet-4: 1000 * $3/MTok
    ("input_only", make_event(inp=1000), Decimal("0.003")),
    # 2. 5m cache write: 1000 * $3 * 1.25 / MTok
    ("cache_write_5m", make_event(cc_5m=1000), Decimal("0.00375")),
    # 3. 1h cache write: 1000 * $3 * 2.0 / MTok
    ("cache_write_1h", make_event(cc_1h=1000), Decimal("0.006")),
    # 4. Mixed TTL write: 500 * $3.75/MTok + 500 * $6/MTok
    ("cache_write_mixed_ttl", make_event(cc_5m=500, cc_1h=500), Decimal("0.004875")),
    # 5. Cache read: 1000 * $3 * 0.10 / MTok
    ("cache_read", make_event(cr=1000), Decimal("0.0003")),
    # 6. Output (estimated): 1000 * $15/MTok
    ("output", make_event(out=1000), Decimal("0.015")),
    # 7. All streams together: 0.003 + 0.00375 + 0.006 + 0.0003 + 0.015
    (
        "all_streams",
        make_event(inp=1000, cc_5m=1000, cc_1h=1000, cr=1000, out=1000),
        Decimal("0.02805"),
    ),
    # 8. Batch tier halves everything: 0.02805 * 0.5
    (
        "all_streams_batch",
        make_event(inp=1000, cc_5m=1000, cc_1h=1000, cr=1000, out=1000, service_tier="batch"),
        Decimal("0.014025"),
    ),
    # 9. Different model rates (haiku $1/$5): 1000*$1 + 1000*$5 per MTok
    ("haiku_rates", make_event(model=HAIKU, inp=1000, out=1000), Decimal("0.006")),
    # 10. Legacy opus-4 rates ($15/$75): 1000*$15 + 1000*$75 per MTok
    ("opus4_rates", make_event(model=OPUS4, inp=1000, out=1000), Decimal("0.09")),
]


@pytest.mark.parametrize("name,event,expected", HAND_COMPUTED, ids=[c[0] for c in HAND_COMPUTED])
def test_hand_computed_costs(name, event, expected, snapshot):
    cost = cost_event(event, snapshot)
    assert cost.total_usd == expected
    assert cost.snapshot_id == "2026-07"  # invariant 4: every $ carries its snapshot


def test_fixture_1_session_total_hand_computed(snapshot):
    """Whole golden session: 0.000045 + 0.0421875 + 0.012 + 0.00744 + 0.009675."""
    events = parse_dir(GOLDEN / "01-simple-session").events
    total = sum((cost_event(e, snapshot).total_usd for e in events), Decimal(0))
    assert total == Decimal("0.0713475")


def test_unknown_model_raises_never_zero(snapshot):
    """Invariant 4: unknown model -> explicit error, never silent $0."""
    event = make_event(model="claude-mystery-9", inp=1000)
    with pytest.raises(UnknownModelError, match="claude-mystery-9"):
        cost_event(event, snapshot)


def test_snapshot_loads_and_is_flagged_unverified(snapshot):
    assert snapshot.snapshot_id == "2026-07"
    assert snapshot.verified is False  # flips to True only after the human gate
    assert snapshot.cache_write_5m == Decimal("1.25")
    assert snapshot.cache_write_1h == Decimal("2.0")
    assert snapshot.cache_read == Decimal("0.10")
    assert snapshot.batch == Decimal("0.50")


def test_latest_snapshot_picks_newest():
    assert latest_snapshot(PRICING).snapshot_id == "2026-07"


def test_malformed_snapshot_rejected(tmp_path):
    (tmp_path / "2026-01.yaml").write_text("snapshot_id: '2026-01'\nmodels: {}\n")
    with pytest.raises(SnapshotError):
        load_snapshot(tmp_path / "2026-01.yaml")
    with pytest.raises(SnapshotError):
        load_snapshot(tmp_path / "does-not-exist.yaml")
    with pytest.raises(SnapshotError):
        latest_snapshot(tmp_path / "empty-dir")


def test_cost_command_on_golden_corpus(capsys):
    code = cli.main(
        ["cost", str(GOLDEN), "--pricing-dir", str(PRICING), "--snapshot", "2026-07"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "snapshot: 2026-07" in out
    assert "UNVERIFIED" in out  # human gate is surfaced, not hidden
    assert "grand total: $" in out


def test_cost_command_unknown_model_fails_loudly(tmp_path, capsys):
    entry = (
        '{"type": "assistant", "uuid": "u1", "sessionId": "s1", "version": "1.0.44",'
        ' "timestamp": "2026-07-01T10:00:00.000Z", "requestId": "r1",'
        ' "message": {"id": "m1", "role": "assistant", "model": "claude-mystery-9",'
        ' "usage": {"input_tokens": 10, "cache_creation_input_tokens": 0,'
        ' "cache_read_input_tokens": 0, "output_tokens": 5}}}'
    )
    (tmp_path / "session.jsonl").write_text(entry + "\n")
    code = cli.main(["cost", str(tmp_path), "--pricing-dir", str(PRICING)])
    out = capsys.readouterr().out
    assert code == 1
    assert "claude-mystery-9" in out and "refusing" in out
