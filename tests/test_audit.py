"""Issue 9 acceptance tests: the audit report."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.ingest.parser import parse_dir
from tokenlens.pricing.engine import load_snapshot
from tokenlens.report.audit_cmd import render_audit

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
SNAPSHOTS = Path(__file__).parent / "snapshots"
PRICING = Path(__file__).parent.parent / "pricing"


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(PRICING / "2026-07.yaml")


def test_golden_file_report(snapshot):
    """Acceptance: golden-file test of the full report on the corpus."""
    report = render_audit(parse_dir(GOLDEN), snapshot)
    assert report == (SNAPSHOTS / "audit_golden.md").read_text()


def test_every_dollar_traceable(snapshot):
    """Acceptance: every $ figure is traceable to a component + snapshot."""
    report = render_audit(parse_dir(GOLDEN), snapshot)
    assert report.count("`2026-07`") >= 4  # spend, prescriptions x2, footer
    # Output dollars are always marked estimated wherever they appear.
    assert "output (estimated)" in report
    assert "Output-token dollars are estimates" in report
    # The unverified pricing snapshot is called out, not hidden.
    assert "UNVERIFIED, human gate pending" in report
    # Prescriptions are ranked by damage and name their trigger component.
    prescriptions = re.findall(r"\d+\. \*\*\$([0-9.]+)\*\* — .+ \(`(\w+)`", report)
    assert [t for _, t in prescriptions] == ["model_change", "version_change"]
    damages = [float(d) for d, _ in prescriptions]
    assert damages == sorted(damages, reverse=True)


@pytest.mark.parametrize(
    "fixture",
    [
        "01-simple-session",
        "02-streaming-duplicates",
        "03-model-switch",
        "04-parent-subagent",
        "05-version-upgrade",
    ],
)
def test_renders_clean_on_each_fixture(fixture, capsys):
    """Acceptance: renders clean on all 5 golden fixtures."""
    code = cli.main(
        [
            "audit",
            str(GOLDEN / fixture),
            "--pricing-dir",
            str(PRICING),
            "--snapshot",
            "2026-07",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("# tokenlens audit")
    assert "## Spend" in out and "## Cache health" in out


def test_sessions_are_anonymized_by_default(snapshot):
    report = render_audit(parse_dir(GOLDEN), snapshot)
    # Full session UUIDs never appear — only 8-char prefixes.
    assert "f3000000-0000-4000-8000-000000000003" not in report
    assert "f3000000" in report


def test_audit_out_writes_file(tmp_path, capsys):
    target = tmp_path / "report.md"
    code = cli.main(
        [
            "audit",
            str(GOLDEN),
            "--pricing-dir",
            str(PRICING),
            "--snapshot",
            "2026-07",
            "--out",
            str(target),
        ]
    )
    assert code == 0
    assert target.read_text() == (SNAPSHOTS / "audit_golden.md").read_text()
    assert "wrote" in capsys.readouterr().out
