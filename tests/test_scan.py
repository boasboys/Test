"""Issue 1 acceptance tests: `tokenlens scan` (RAW/UNCORRECTED)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.ingest.parser import parse_dir

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
SNAPSHOTS = Path(__file__).parent / "snapshots"


def test_scan_runs_on_full_golden_corpus_without_crashing(capsys):
    assert cli.main(["scan", str(GOLDEN)]) == 0
    out = capsys.readouterr().out
    assert "CORRECTED token accounting" in out
    # All six sessions (5 fixtures, fixture 4 contributes two) appear.
    for prefix in ("f1", "f2", "f3", "f4", "f5"):
        assert f"{prefix}000000-" in out


def test_scan_snapshot_fixture_1(capsys):
    """Issue 1 acceptance: snapshot test against fixture 1."""
    assert cli.main(["scan", str(GOLDEN / "01-simple-session")]) == 0
    expected = (SNAPSHOTS / "scan_01_simple_session.txt").read_text()
    assert capsys.readouterr().out == expected


def test_scan_counts_and_reports_malformed_lines(capsys):
    cli.main(["scan", str(GOLDEN / "01-simple-session")])
    assert "malformed (skipped): 1" in capsys.readouterr().out


def test_scan_raw_totals_match_expected_ground_truth():
    """Raw (pre-dedup) parser totals equal each fixture's hand-computed totals_raw."""
    for fixture_dir in sorted(d for d in GOLDEN.iterdir() if d.is_dir()):
        expected = json.loads((fixture_dir / "expected.json").read_text())
        result = parse_dir(fixture_dir)
        assert len(result.events) == expected["events_raw"], fixture_dir.name
        got = {
            "input_tokens": sum(e.input_tokens for e in result.events),
            "cache_creation_input_tokens": sum(e.cache_creation_tokens for e in result.events),
            "cache_read_input_tokens": sum(e.cache_read_tokens for e in result.events),
            "output_tokens": sum(e.output_tokens for e in result.events),
        }
        assert got == expected["totals_raw"], fixture_dir.name
        assert result.malformed_lines == expected["malformed_lines"], fixture_dir.name
        assert result.lines_total == expected["line_count"], fixture_dir.name


def test_scan_survives_hostile_files(tmp_path):
    """Invariant 6: malformed lines skip+count; empty and junk files don't crash."""
    (tmp_path / "empty.jsonl").write_text("")
    (tmp_path / "junk.jsonl").write_text('{"broken\nnull\n[1, 2, 3]\n"just a string"\n')
    result = parse_dir(tmp_path)
    assert result.events == []
    # null / [1,2,3] / "just a string" parse as JSON but are not dicts.
    assert result.malformed_lines == 4
    assert result.files_scanned == 2


def test_scan_missing_directory_errors_cleanly(tmp_path, capsys):
    assert cli.main(["scan", str(tmp_path / "nope")]) == 1
    assert "not a directory" in capsys.readouterr().out


@pytest.mark.parametrize("fixture", ["02-streaming-duplicates"])
def test_scan_shows_raw_and_corrected_side_by_side(fixture, capsys):
    """Issue 2: raw columns are kept — fixture 2's inflated 755 next to the true 530."""
    cli.main(["scan", str(GOLDEN / fixture)])
    out = capsys.readouterr().out
    assert "755" in out  # raw (uncorrected) output_tokens
    assert "530" in out  # corrected output_tokens
    assert "dedup rate: 50.0%" in out
