"""Issue 6 acceptance tests: deterministic task-type classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.classify.turns import CATEGORIES, classify_sessions, classify_turn
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import parse_dir

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden"
TASKS = FIXTURES / "tasks"
PRICING = Path(__file__).parent.parent / "pricing"


def labeled_turns():
    labels = json.loads((TASKS / "labels.json").read_text())["labels"]
    events = sorted(parse_dir(TASKS).events, key=lambda e: e.timestamp)
    assert len(events) == len(labels) == 50
    return list(zip(events, labels, strict=True))


def test_50_turn_fixture_reaches_90_percent_agreement():
    """Acceptance: >=90% agreement with the hand-labeled 50-turn fixture."""
    turns = labeled_turns()
    agreements = sum(1 for event, label in turns if classify_turn(event) == label)
    assert agreements / len(turns) >= 0.90
    # Log exact agreement so regressions are visible in failure output.
    mismatches = [
        (e.event_uuid, label, classify_turn(e))
        for e, label in turns
        if classify_turn(e) != label
    ]
    assert mismatches == [], mismatches  # currently 100% — any drop is a regression


def test_every_category_appears_in_fixture():
    turns = labeled_turns()
    assert {label for _, label in turns} == set(CATEGORIES)


def test_category_shares_sum_to_100_percent():
    """Acceptance: category shares sum to 100% of classified turns."""
    events = dedup_last_wins(parse_dir(TASKS).events)
    categories, stats = classify_sessions(events)
    assert len(categories) == len(events)  # every turn classified, none dropped
    assert sum(s.turns for s in stats.values()) == len(events)


def test_one_shot_rate_definition():
    """Runs of length 1 are one-shots; longer runs are not."""
    events = dedup_last_wins(parse_dir(TASKS).events)
    _, stats = classify_sessions(events)
    for category in CATEGORIES:
        s = stats[category]
        assert s.total_runs >= 1, category
        rate = s.one_shot_rate
        assert rate is not None and 0.0 <= rate <= 1.0
    # Fixture tail has one adjacent conversation pair (pools drain unevenly):
    # 10 turns in 9 runs, 8 of them one-shots.
    assert stats["conversation"].one_shot_rate == pytest.approx(8 / 9)


def test_debugging_beats_testing_precedence():
    """Edit->Bash(pytest)->Edit is debugging, not testing."""
    events = sorted(parse_dir(TASKS).events, key=lambda e: e.timestamp)
    debug_events = [
        e
        for e in events
        if "pytest" in " ".join(e.bash_commands) and e.tool_names[0] == "Edit"
    ]
    assert debug_events, "fixture should contain an Edit->pytest->Edit turn"
    assert all(classify_turn(e) == "debugging" for e in debug_events)


def test_golden_fixtures_classify_cleanly():
    """Golden corpus: text-only turns are conversation; Task spawn is delegation."""
    events = dedup_last_wins(parse_dir(GOLDEN).events)
    categories, stats = classify_sessions(events)
    assert sum(s.turns for s in stats.values()) == len(events)
    spawn = next(e for e in events if "Task" in e.tool_names)
    assert categories[spawn.event_uuid] == "delegation"


def test_tasks_command_reports_benchmarks(capsys):
    """Acceptance: corpus report shows conversation% and exploration%."""
    code = cli.main(
        ["tasks", str(TASKS), "--pricing-dir", str(PRICING), "--snapshot", "2026-07"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "conversation: 20.0% (benchmark 25-56%)" in out
    assert "exploration: 16.0% (benchmark ~47%)" in out
    assert "snapshot: 2026-07" in out
    assert "one-shot" in out


def test_tasks_command_missing_directory(tmp_path, capsys):
    assert cli.main(["tasks", str(tmp_path / "nope"), "--pricing-dir", str(PRICING)]) == 1
