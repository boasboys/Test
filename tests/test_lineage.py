"""Issue 7 acceptance tests: sub-agent lineage joins and fan-out metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.ingest.accounting import dedup_last_wins, stream_totals
from tokenlens.ingest.lineage import build_families, fan_out, total_tokens
from tokenlens.ingest.parser import parse_dir

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
FIXTURES = sorted(d.name for d in GOLDEN.iterdir() if d.is_dir())


def test_fixture_4_joins_child_to_parent():
    """Acceptance: fixture 4 joins correctly via parentToolUseId/agentId."""
    expected = json.loads((GOLDEN / "04-parent-subagent" / "expected.json").read_text())
    lineage = expected["lineage"]
    result = parse_dir(GOLDEN / "04-parent-subagent")

    meta = result.session_meta[lineage["child_session"]]
    assert meta.is_sidechain
    assert meta.agent_id == lineage["agent_id"]
    assert meta.parent_tool_use_id == lineage["parent_tool_use_id"]

    (family,) = build_families(result)
    assert family.root_session == lineage["parent_session"]
    assert family.child_sessions == [lineage["child_session"]]
    assert not family.orphaned


def test_fixture_4_no_token_counted_twice():
    """Acceptance property: family total = sum of deduped events."""
    expected = json.loads((GOLDEN / "04-parent-subagent" / "expected.json").read_text())
    result = parse_dir(GOLDEN / "04-parent-subagent")
    (family,) = build_families(result)
    want = expected["lineage"]["family_totals_deduped"]
    got = stream_totals(family.events)
    assert got["input_tokens"] == want["input_tokens"]
    assert got["cache_creation_tokens"] == want["cache_creation_input_tokens"]
    assert got["cache_read_tokens"] == want["cache_read_input_tokens"]
    assert got["output_tokens"] == want["output_tokens"]


@pytest.mark.parametrize("name", FIXTURES)
def test_families_partition_deduped_events(name):
    """Property on every fixture: families cover each deduped event exactly once."""
    result = parse_dir(GOLDEN / name)
    families = build_families(result)
    family_events = [e for f in families for e in f.events]
    deduped = dedup_last_wins(result.events)
    assert sorted(e.event_uuid for e in family_events) == sorted(e.event_uuid for e in deduped)
    assert total_tokens(family_events) == total_tokens(deduped)


def test_fixture_4_fan_out_metrics():
    result = parse_dir(GOLDEN / "04-parent-subagent")
    (family,) = build_families(result)
    metrics = fan_out(family)
    # Hand-computed from expected.json: root 33,092 tok; child 18,758 tok.
    assert metrics.subagent_count == 1
    assert metrics.family_tokens == 33092 + 18758
    assert metrics.subagent_tokens == 18758
    assert metrics.subagent_share == pytest.approx(18758 / 51850)
    assert metrics.fanout_multiplier == pytest.approx(51850 / 33092)
    assert metrics.haiku_share == 1.0  # the sub-agent ran on Haiku


def test_standalone_sessions_are_single_member_families():
    result = parse_dir(GOLDEN / "01-simple-session")
    (family,) = build_families(result)
    assert family.child_sessions == []
    metrics = fan_out(family)
    assert metrics.subagent_count == 0
    assert metrics.subagent_share == 0.0
    assert metrics.fanout_multiplier == 1.0


def test_orphaned_child_becomes_own_flagged_root(tmp_path):
    """A sidechain whose parentToolUseId never appears must not vanish."""
    src = GOLDEN / "04-parent-subagent" / "subagent.jsonl"
    (tmp_path / "orphan.jsonl").write_text(src.read_text())
    result = parse_dir(tmp_path)
    (family,) = build_families(result)
    assert family.orphaned
    assert family.child_sessions == []
    assert len(family.events) == 2  # its tokens still count


def test_scan_fanout_reports_corpus_distribution(capsys):
    """Acceptance: corpus fan-out distribution reported."""
    assert cli.main(["scan", str(GOLDEN), "--fanout"]) == 0
    out = capsys.readouterr().out
    assert "Sub-agent fan-out" in out
    # 6 sessions collapse into 5 families: fixture 4's child joins its parent.
    assert "families: 5   with subagents: 1   max fan-out: 1" in out
    assert "f4000000-0000-4000-8000-00000000004a" in out
    assert "100.0%" in out  # haiku share of the one sub-agent family
