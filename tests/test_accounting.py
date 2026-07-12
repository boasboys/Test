"""Issue 2 acceptance tests: last-wins dedup and corrected accounting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenlens.ingest.accounting import dedup_last_wins, dedup_rate, stream_totals
from tokenlens.ingest.parser import STREAMS, parse_dir

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
FIXTURES = sorted(d.name for d in GOLDEN.iterdir() if d.is_dir())


def events_for(name: str):
    return parse_dir(GOLDEN / name).events


def test_fixture_2_dedups_to_exactly_known_events():
    """Acceptance: fixture 2 dedups to exactly N known events."""
    expected = json.loads((GOLDEN / "02-streaming-duplicates" / "expected.json").read_text())
    raw = events_for("02-streaming-duplicates")
    deduped = dedup_last_wins(raw)
    assert len(raw) == expected["events_raw"] == 6
    assert len(deduped) == expected["events_deduped"] == 3
    assert stream_totals(deduped) == {
        "input_tokens": expected["totals_deduped"]["input_tokens"],
        "cache_creation_tokens": expected["totals_deduped"]["cache_creation_input_tokens"],
        "cache_read_tokens": expected["totals_deduped"]["cache_read_input_tokens"],
        "output_tokens": expected["totals_deduped"]["output_tokens"],
    }


def test_last_wins_not_first_wins():
    """The survivor of a duplicate run carries the FINAL output_tokens count."""
    deduped = dedup_last_wins(events_for("02-streaming-duplicates"))
    by_message = {e.message_id: e for e in deduped}
    assert by_message["msg_f2_a1"].output_tokens == 260  # not 40 (first write)
    assert by_message["msg_f2_a2"].output_tokens == 180  # not 55
    # The surviving entry is literally the last line written, not a merge.
    assert by_message["msg_f2_a1"].event_uuid == "f2-a-01c"


@pytest.mark.parametrize("name", FIXTURES)
def test_dedup_is_idempotent(name):
    """Property: dedup(dedup(x)) == dedup(x)."""
    once = dedup_last_wins(events_for(name))
    twice = dedup_last_wins(once)
    assert twice == once


@pytest.mark.parametrize("name", FIXTURES)
def test_corrected_totals_never_exceed_raw(name):
    """Property: corrected totals <= raw totals, per stream."""
    raw = events_for(name)
    ded = dedup_last_wins(raw)
    raw_totals, ded_totals = stream_totals(raw), stream_totals(ded)
    for stream in STREAMS:
        assert ded_totals[stream] <= raw_totals[stream]


@pytest.mark.parametrize("name", FIXTURES)
def test_deduped_matches_expected_ground_truth(name):
    expected = json.loads((GOLDEN / name / "expected.json").read_text())
    deduped = dedup_last_wins(events_for(name))
    assert len(deduped) == expected["events_deduped"]
    got = stream_totals(deduped)
    want = expected["totals_deduped"]
    assert got["input_tokens"] == want["input_tokens"]
    assert got["cache_creation_tokens"] == want["cache_creation_input_tokens"]
    assert got["cache_read_tokens"] == want["cache_read_input_tokens"]
    assert got["output_tokens"] == want["output_tokens"]


def test_dedup_preserves_distinct_events_with_shared_message_id():
    """Keying is the PAIR (message_id, request_id): same message_id under
    different request_ids (e.g. a retried request) must not collapse."""
    import dataclasses

    raw = events_for("01-simple-session")
    # Simulate a retry of the first call under a new request id.
    retried = raw + [dataclasses.replace(raw[0], request_id="req_f1_r1_retry")]
    assert len(dedup_last_wins(retried)) == len(raw) + 1


def test_dedup_rate():
    assert dedup_rate(6, 3) == 0.5
    assert dedup_rate(3, 3) == 0.0
    assert dedup_rate(0, 0) == 0.0


def test_corpus_wide_dedup_rate_reported(capsys):
    """Acceptance: scan reports the corpus-wide dedup rate."""
    from tokenlens import cli

    assert cli.main(["scan", str(GOLDEN)]) == 0
    out = capsys.readouterr().out
    # 23 raw events -> 20 deduped across the golden corpus.
    assert "23 raw" in out and "20 corrected" in out
    assert "dedup rate: 13.0%" in out
