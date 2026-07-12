"""Issue 5 acceptance tests: bust trigger attribution + counterfactual damage."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.forensics.attribution import attribute_all, unknown_rate
from tokenlens.ingest.parser import parse_dir
from tokenlens.pricing.engine import load_snapshot

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
PRICING = Path(__file__).parent.parent / "pricing"

SONNET = "claude-sonnet-4-20250514"


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(PRICING / "2026-07.yaml")


def _line(
    kind: str,
    session: str,
    uuid: str,
    ts: str,
    *,
    model: str = SONNET,
    version: str = "1.0.44",
    inp: int = 5,
    cc: int = 0,
    cr: int = 0,
    out: int = 100,
    content: list | None = None,
    extra: dict | None = None,
) -> str:
    entry: dict = {
        "sessionId": session,
        "version": version,
        "type": kind,
        "uuid": uuid,
        "timestamp": ts,
    }
    if kind == "assistant":
        entry["requestId"] = f"req_{uuid}"
        entry["message"] = {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "model": model,
            "content": content or [{"type": "text", "text": "x"}],
            "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": cc,
                "cache_read_input_tokens": cr,
                "output_tokens": out,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": cc,
                    "ephemeral_1h_input_tokens": 0,
                },
            },
        }
    elif kind == "user":
        entry["message"] = {"role": "user", "content": content or [{"type": "text", "text": "x"}]}
    if extra:
        entry.update(extra)
    return json.dumps(entry)


def write_session(tmp_path: Path, lines: list[str]) -> Path:
    (tmp_path / "session.jsonl").write_text("\n".join(lines) + "\n")
    return tmp_path


def attribute_dir(path: Path, snapshot) -> list:
    return attribute_all(parse_dir(path), snapshot)


def test_fixture_3_attributes_model_change(snapshot):
    """Acceptance: fixture 3 attributes correctly (model_change)."""
    (attr,) = attribute_dir(GOLDEN / "03-model-switch", snapshot)
    assert attr.trigger == "model_change"
    assert attr.bust.turn == 4
    assert attr.snapshot_id == "2026-07"
    # Hand-computed on opus-4 ($15/MTok): actual (5 + 14900*1.25)*15/1e6
    # minus counterfactual 14905*1.5/1e6 = 0.2794500 - 0.0223575.
    assert attr.damage_usd == Decimal("0.2570925")


def test_fixture_5_attributes_version_change(snapshot):
    """Acceptance: fixture 5 attributes correctly (version_change)."""
    (attr,) = attribute_dir(GOLDEN / "05-version-upgrade", snapshot)
    assert attr.trigger == "version_change"
    assert attr.bust.turn == 3
    # Hand-computed on sonnet-4 ($3/MTok): (6*3 + 13600*3.75)/1e6 - 13606*0.3/1e6.
    assert attr.damage_usd == Decimal("0.0469362")


def test_ttl_gap_attribution(tmp_path, snapshot):
    """A >5-minute gap with no other evidence attributes to ttl_gap."""
    s = "ttl-session"
    write_session(
        tmp_path,
        [
            _line("assistant", s, "a1", "2026-07-01T10:00:00.000Z", cc=10000, cr=0),
            _line("assistant", s, "a2", "2026-07-01T10:01:00.000Z", cc=300, cr=10000),
            # 12-minute gap — the 5m cache is long gone.
            _line("assistant", s, "a3", "2026-07-01T10:13:00.000Z", cc=10300, cr=0),
        ],
    )
    (attr,) = attribute_dir(tmp_path, snapshot)
    assert attr.trigger == "ttl_gap"
    assert attr.bust.turn == 3


def test_image_attribution(tmp_path, snapshot):
    """An image block landing between turns attributes to image."""
    s = "img-session"
    write_session(
        tmp_path,
        [
            _line("assistant", s, "a1", "2026-07-01T10:00:00.000Z", cc=10000, cr=0),
            _line("assistant", s, "a2", "2026-07-01T10:01:00.000Z", cc=300, cr=10000),
            _line(
                "user",
                s,
                "u3",
                "2026-07-01T10:02:00.000Z",
                content=[{"type": "image", "source": {"type": "base64"}}],
            ),
            _line("assistant", s, "a3", "2026-07-01T10:02:30.000Z", cc=10300, cr=0),
        ],
    )
    (attr,) = attribute_dir(tmp_path, snapshot)
    assert attr.trigger == "image"


def test_compact_attribution_takes_precedence(tmp_path, snapshot):
    """A compact marker wins even when other evidence is present."""
    s = "compact-session"
    write_session(
        tmp_path,
        [
            _line("assistant", s, "a1", "2026-07-01T10:00:00.000Z", cc=10000, cr=0),
            _line("assistant", s, "a2", "2026-07-01T10:01:00.000Z", cc=300, cr=10000),
            json.dumps(
                {
                    "sessionId": s,
                    "type": "system",
                    "subtype": "compact_boundary",
                    "uuid": "sys1",
                    "timestamp": "2026-07-01T10:02:00.000Z",
                }
            ),
            # Model ALSO changes — compact still wins by precedence.
            _line(
                "assistant",
                s,
                "a3",
                "2026-07-01T10:02:30.000Z",
                model="claude-opus-4-20250514",
                cc=10300,
                cr=0,
            ),
        ],
    )
    (attr,) = attribute_dir(tmp_path, snapshot)
    assert attr.trigger == "compact"


def test_unknown_attribution_and_rate(tmp_path, snapshot):
    """No evidence at all -> unknown, and the unknown rate reflects it."""
    s = "unknown-session"
    write_session(
        tmp_path,
        [
            _line("assistant", s, "a1", "2026-07-01T10:00:00.000Z", cc=10000, cr=0),
            _line("assistant", s, "a2", "2026-07-01T10:01:00.000Z", cc=300, cr=10000),
            _line("assistant", s, "a3", "2026-07-01T10:02:00.000Z", cc=10300, cr=0),
        ],
    )
    attributions = attribute_dir(tmp_path, snapshot)
    (attr,) = attributions
    assert attr.trigger == "unknown"
    assert unknown_rate(attributions) == 1.0
    assert unknown_rate([]) == 0.0


def test_golden_corpus_unknown_rate_is_zero(snapshot):
    """Both golden busts have clean evidence — unknown rate 0%."""
    attributions = []
    for fixture in sorted(d for d in GOLDEN.iterdir() if d.is_dir()):
        attributions.extend(attribute_dir(fixture, snapshot))
    assert len(attributions) == 2
    assert unknown_rate(attributions) == 0.0
    assert {a.trigger for a in attributions} == {"model_change", "version_change"}


def test_cache_triggers_cli_renders_table(capsys):
    code = cli.main(
        [
            "cache",
            str(GOLDEN),
            "--triggers",
            "--pricing-dir",
            str(PRICING),
            "--snapshot",
            "2026-07",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Bust trigger attribution" in out
    assert "model_change" in out and "version_change" in out
    assert "$0.2571" in out  # fixture 3 damage, rendered at 4dp
    assert "unknown rate: 0%" in out
