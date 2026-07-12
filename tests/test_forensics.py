"""Issue 4 acceptance tests: cache health, bust detection, histogram."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.forensics.health import BustEvent, cache_health, detect_busts
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, parse_dir

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def session_events(fixture: str) -> dict[str, list[Event]]:
    deduped = dedup_last_wins(parse_dir(GOLDEN / fixture).events)
    sessions: dict[str, list[Event]] = {}
    for event in deduped:
        sessions.setdefault(event.session_id, []).append(event)
    return sessions


def mk_event(turn: int, cc: int, cr: int, inp: int = 5, out: int = 50) -> Event:
    return Event(
        session_id="synthetic",
        event_uuid=f"u{turn}",
        parent_uuid=None,
        is_sidechain=False,
        agent_id=None,
        message_id=f"m{turn}",
        request_id=f"r{turn}",
        model="claude-sonnet-4-20250514",
        version="1.0.44",
        timestamp=f"2026-07-01T10:{turn:02d}:00.000Z",
        input_tokens=inp,
        cache_creation_tokens=cc,
        cache_creation_5m=cc,
        cache_creation_1h=0,
        cache_read_tokens=cr,
        output_tokens=out,
        service_tier="standard",
        content_types=("text",),
        tool_names=(),
        tool_use_ids=(),
        bash_commands=(),
        source_file="synthetic",
    )


def test_fixture_3_yields_exactly_one_bust_at_known_turn():
    """Acceptance: fixture 3 -> exactly 1 bust at the turn in expected.json."""
    expected = json.loads((GOLDEN / "03-model-switch" / "expected.json").read_text())
    (want,) = expected["bust_events"]
    (events,) = session_events("03-model-switch").values()
    (bust,) = detect_busts(events)
    assert bust.turn == want["turn"] == 4
    assert bust.message_id == want["message_id"]
    assert bust.kind == "read_drop"


def test_healthy_fixture_yields_zero_busts():
    """Acceptance: fixture 1 (healthy session) -> 0 bust events."""
    (events,) = session_events("01-simple-session").values()
    assert detect_busts(events) == []


@pytest.mark.parametrize("fixture", ["02-streaming-duplicates", "04-parent-subagent"])
def test_other_fixtures_have_no_false_positives(fixture):
    for events in session_events(fixture).values():
        assert detect_busts(events) == []


def test_fixture_5_busts_at_version_change_turn():
    expected = json.loads((GOLDEN / "05-version-upgrade" / "expected.json").read_text())
    (want,) = expected["bust_events"]
    (events,) = session_events("05-version-upgrade").values()
    (bust,) = detect_busts(events)
    assert bust.turn == want["turn"] == 3
    assert bust.message_id == want["message_id"]
    assert bust.kind == "read_drop"


def test_cache_health_formula_hand_computed():
    """Fixture 1: 24800 / (24800 + 13250 + 15)."""
    (events,) = session_events("01-simple-session").values()
    assert cache_health(events) == pytest.approx(24800 / 38065)


def test_cache_health_bounds_and_empty():
    assert cache_health([]) is None
    assert cache_health([mk_event(1, cc=0, cr=0, inp=0, out=10)]) is None
    for fixture in ("01-simple-session", "03-model-switch", "04-parent-subagent"):
        for events in session_events(fixture).values():
            score = cache_health(events)
            assert score is not None and 0.0 <= score <= 1.0


def test_first_turn_never_busts():
    """First-turn cache_creation with zero read is expected, not a bust."""
    assert detect_busts([mk_event(1, cc=20000, cr=0)]) == []


def test_creation_dominant_detected():
    events = [
        mk_event(1, cc=10000, cr=0),
        mk_event(2, cc=8000, cr=3000),  # creating more than it reads mid-session
    ]
    (bust,) = detect_busts(events)
    assert bust == BustEvent(
        session_id="synthetic",
        turn=2,
        message_id="m2",
        timestamp="2026-07-01T10:02:00.000Z",
        kind="creation_dominant",
    )


def test_regression_signature_flat_read_growing_creation():
    """Flat cache_read + growing cache_creation for >= 3 turns -> one regression."""
    events = [
        mk_event(1, cc=10000, cr=0),
        mk_event(2, cc=100, cr=10000),
        mk_event(3, cc=200, cr=10000),
        mk_event(4, cc=300, cr=10050),  # within the 5% flat band
    ]
    (bust,) = detect_busts(events)
    assert bust.kind == "regression"
    assert bust.turn == 2  # flagged at the start of the run


def test_no_regression_when_creation_shrinks():
    events = [
        mk_event(1, cc=10000, cr=0),
        mk_event(2, cc=300, cr=10000),
        mk_event(3, cc=200, cr=10000),
        mk_event(4, cc=100, cr=10000),
    ]
    assert detect_busts(events) == []


def test_cache_command_renders_histogram_on_corpus(capsys):
    """Acceptance: histogram renders on the (golden) corpus."""
    assert cli.main(["cache", str(GOLDEN)]) == 0
    out = capsys.readouterr().out
    assert "fleet cache-health histogram" in out
    assert "85% healthy reference" in out
    assert "92% excellent reference" in out
    assert "bust events: 2" in out  # fixture 3 + fixture 5
    assert "below 85% health: 6/6" in out  # short synthetic sessions all score low
    assert "t4:read_drop" in out and "t3:read_drop" in out


def test_cache_command_missing_directory(tmp_path, capsys):
    assert cli.main(["cache", str(tmp_path / "nope")]) == 1
    assert "not a directory" in capsys.readouterr().out
