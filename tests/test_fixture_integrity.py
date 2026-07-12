"""Fixture-integrity tests: recompute every expected.json from raw lines.

These tests are the tripwire for CLAUDE.md invariant 1 ("fixtures are sacred"):
any edit to a golden fixture that changes its structure or totals fails here.
They also pin the dedup contract (invariant 5: last-wins by
(message.id, requestId)) against ground truth before Issue 2 implements it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
STREAMS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)

FIXTURES = sorted(d.name for d in GOLDEN.iterdir() if d.is_dir())


def load_fixture(name: str) -> tuple[dict, list, int, int]:
    """Parse all *.jsonl in a fixture dir; return (expected, events, lines, malformed)."""
    d = GOLDEN / name
    expected = json.loads((d / "expected.json").read_text())
    events: list[dict] = []
    line_count = malformed = 0
    for path in sorted(d.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            line_count += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if entry.get("type") == "assistant" and "usage" in entry.get("message", {}):
                events.append(entry)
    return expected, events, line_count, malformed


def dedup_last_wins(events: list[dict]) -> list[dict]:
    """Reference dedup: last-wins by (message.id, requestId)."""
    survivors: dict[tuple[str, str], dict] = {}
    for e in events:
        survivors[(e["message"]["id"], e["requestId"])] = e
    return list(survivors.values())


def totals(events: list[dict]) -> dict[str, int]:
    return {s: sum(e["message"]["usage"][s] for e in events) for s in STREAMS}


def test_all_five_fixtures_present():
    assert FIXTURES == [
        "01-simple-session",
        "02-streaming-duplicates",
        "03-model-switch",
        "04-parent-subagent",
        "05-version-upgrade",
    ]


@pytest.mark.parametrize("name", FIXTURES)
def test_expected_matches_recomputation(name):
    expected, events, line_count, malformed = load_fixture(name)
    deduped = dedup_last_wins(events)

    assert line_count == expected["line_count"]
    assert malformed == expected["malformed_lines"]
    assert len(events) == expected["events_raw"]
    assert len(deduped) == expected["events_deduped"]
    assert totals(events) == expected["totals_raw"]
    assert totals(deduped) == expected["totals_deduped"]
    assert sorted({e["message"]["model"] for e in events}) == expected["models"]
    assert sorted({e["version"] for e in events}) == expected["versions"]
    assert sorted({e["sessionId"] for e in events}) == expected["sessions"]


@pytest.mark.parametrize("name", FIXTURES)
def test_corrected_totals_never_exceed_raw(name):
    _, events, _, _ = load_fixture(name)
    raw, ded = totals(events), totals(dedup_last_wins(events))
    for stream in STREAMS:
        assert ded[stream] <= raw[stream]


@pytest.mark.parametrize("name", FIXTURES)
def test_usage_carries_5m_1h_split(name):
    """Every event splits cache_creation into ephemeral 5m/1h that sum exactly."""
    _, events, _, _ = load_fixture(name)
    for e in events:
        usage = e["message"]["usage"]
        split = usage["cache_creation"]
        assert (
            split["ephemeral_5m_input_tokens"] + split["ephemeral_1h_input_tokens"]
            == usage["cache_creation_input_tokens"]
        )


def test_fixture_2_dedups_to_known_event_count():
    """The Issue 2 headline case: 6 streaming entries collapse to 3 API calls."""
    expected, events, _, _ = load_fixture("02-streaming-duplicates")
    deduped = dedup_last_wins(events)
    assert len(events) == 6
    assert len(deduped) == 3
    # Last-wins, not first-wins: turn 1's survivor carries the final output count.
    turn1 = next(e for e in deduped if e["message"]["id"] == "msg_f2_a1")
    assert turn1["message"]["usage"]["output_tokens"] == 260
    assert expected["totals_deduped"]["output_tokens"] == 530


def test_fixture_1_five_minute_and_one_hour_split():
    expected, events, _, _ = load_fixture("01-simple-session")
    split = expected["cache_creation_split_deduped"]
    got_5m = sum(
        e["message"]["usage"]["cache_creation"]["ephemeral_5m_input_tokens"] for e in events
    )
    got_1h = sum(
        e["message"]["usage"]["cache_creation"]["ephemeral_1h_input_tokens"] for e in events
    )
    assert {"ephemeral_5m": got_5m, "ephemeral_1h": got_1h} == split


def test_fixture_3_bust_turn_is_model_switch():
    expected, events, _, _ = load_fixture("03-model-switch")
    (bust,) = expected["bust_events"]
    assert bust["trigger"] == "model_change"
    ordered = sorted(events, key=lambda e: e["timestamp"])
    bust_event = ordered[bust["turn"] - 1]
    prev_event = ordered[bust["turn"] - 2]
    assert bust_event["message"]["id"] == bust["message_id"]
    assert bust_event["message"]["usage"]["cache_read_input_tokens"] == 0
    assert bust_event["message"]["model"] != prev_event["message"]["model"]


def test_fixture_4_lineage_and_no_double_count():
    expected, events, _, _ = load_fixture("04-parent-subagent")
    lineage = expected["lineage"]
    parent_events = [e for e in events if e["sessionId"] == lineage["parent_session"]]
    child_events = [e for e in events if e["sessionId"] == lineage["child_session"]]
    assert parent_events and child_events
    assert all(e.get("isSidechain") for e in child_events)
    assert all(e.get("agentId") == lineage["agent_id"] for e in child_events)
    # The spawning tool_use exists in the parent.
    spawns = [
        block
        for e in parent_events
        for block in e["message"]["content"]
        if block.get("type") == "tool_use" and block.get("id") == lineage["parent_tool_use_id"]
    ]
    assert len(spawns) == 1 and spawns[0]["name"] == "Task"
    # Family total = sum of deduped events (Issue 7 property, pinned here).
    family = totals(dedup_last_wins(events))
    assert family == lineage["family_totals_deduped"]


def test_fixture_5_bust_turn_is_version_change():
    expected, events, _, _ = load_fixture("05-version-upgrade")
    (bust,) = expected["bust_events"]
    assert bust["trigger"] == "version_change"
    ordered = sorted(events, key=lambda e: e["timestamp"])
    bust_event = ordered[bust["turn"] - 1]
    prev_event = ordered[bust["turn"] - 2]
    assert bust_event["message"]["id"] == bust["message_id"]
    assert bust_event["message"]["usage"]["cache_read_input_tokens"] == 0
    assert bust_event["version"] != prev_event["version"]
