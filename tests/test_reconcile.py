"""Issue 8 acceptance tests: mocked-API reconciliation, key hygiene, tie-out."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tokenlens import cli
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import parse_dir
from tokenlens.pricing.engine import load_snapshot
from tokenlens.reconcile import api_client
from tokenlens.reconcile.tieout import (
    jsonl_daily_dollars,
    normalize_api_buckets,
    tie_out,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
PRICING = Path(__file__).parent.parent / "pricing"

FAKE_KEY = "sk-ant-admin-TEST-NOT-A-REAL-KEY"

# Fixture 1's hand-computed daily dollars (sonnet-4, 2026-07-01).
F1_INPUT = Decimal("0.000045")
F1_CACHE_WRITE = Decimal("0.0541875")  # 11250*3.75/1e6 + 2000*6/1e6
F1_CACHE_READ = Decimal("0.00744")
F1_OUTPUT = Decimal("0.009675")


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(PRICING / "2026-07.yaml")


def bucket(date: str, amounts: dict[str, str]) -> dict:
    return {
        "starting_at": f"{date}T00:00:00Z",
        "ending_at": f"{date}T23:59:59Z",
        "results": [
            {"token_type": token_type, "currency": "USD", "amount": amount}
            for token_type, amount in amounts.items()
        ],
    }


def test_jsonl_daily_dollars_hand_computed(snapshot):
    events = dedup_last_wins(parse_dir(GOLDEN / "01-simple-session").events)
    daily = jsonl_daily_dollars(events, snapshot)
    assert daily[("2026-07-01", "input")] == F1_INPUT
    assert daily[("2026-07-01", "cache_write")] == F1_CACHE_WRITE
    assert daily[("2026-07-01", "cache_read")] == F1_CACHE_READ
    assert daily[("2026-07-01", "output")] == F1_OUTPUT


def test_normalize_api_buckets_merges_ttl_split_and_skips_unknown():
    buckets = [
        bucket(
            "2026-07-01",
            {
                "uncached_input_tokens": "1.00",
                "cache_creation.ephemeral_5m_input_tokens": "2.00",
                "cache_creation.ephemeral_1h_input_tokens": "0.50",
                "cache_read_input_tokens": "0.25",
                "output_tokens": "3.00",
                "web_search_requests": "9.99",  # non-token cost type: ignored
            },
        )
    ]
    daily = normalize_api_buckets(buckets)
    assert daily[("2026-07-01", "input")] == Decimal("1.00")
    assert daily[("2026-07-01", "cache_write")] == Decimal("2.50")  # 5m + 1h merged
    assert daily[("2026-07-01", "cache_read")] == Decimal("0.25")
    assert daily[("2026-07-01", "output")] == Decimal("3.00")
    assert len(daily) == 4


def test_normalize_rejects_unparseable_amounts():
    with pytest.raises(ValueError, match="unparseable"):
        normalize_api_buckets([bucket("2026-07-01", {"uncached_input_tokens": "oops"})])


def test_tie_out_classifications(snapshot):
    jsonl = {
        ("2026-07-01", "input"): Decimal("1.00"),
        ("2026-07-01", "cache_read"): Decimal("1.00"),
        ("2026-07-02", "input"): Decimal("1.00"),
        ("2026-07-01", "output"): Decimal("5.00"),
    }
    api = {
        ("2026-07-01", "input"): Decimal("1.01"),  # +1%: inside tolerance
        ("2026-07-01", "cache_read"): Decimal("0.80"),  # jsonl 25% above api
        ("2026-07-03", "cache_write"): Decimal("2.00"),  # api-only day
    }
    ledger = {(e.date, e.stream): e for e in tie_out(jsonl, api)}
    assert ledger[("2026-07-01", "input")].classification == "within_tolerance"
    assert ledger[("2026-07-01", "cache_read")].classification == "jsonl_above_api"
    assert ledger[("2026-07-02", "input")].classification == "jsonl_only"
    assert ledger[("2026-07-03", "cache_write")].classification == "api_only"
    out = ledger[("2026-07-01", "output")]
    assert out.classification == "estimated_output" and out.divergence is None
    # jsonl_below_api: local undercount beyond tolerance
    below = tie_out({("2026-07-01", "input"): Decimal("0.50")},
                    {("2026-07-01", "input"): Decimal("1.00")})
    assert below[0].classification == "jsonl_below_api"


def test_fetch_paginates_and_sends_key_header(monkeypatch):
    monkeypatch.setenv(api_client.ADMIN_KEY_ENV_VAR, FAKE_KEY)
    calls: list[tuple[str, dict]] = []

    def fake_fetch(url: str, headers: dict) -> dict:
        calls.append((url, headers))
        if "page=" not in url:
            return {"data": [bucket("2026-07-01", {})], "has_more": True, "next_page": "p2"}
        return {"data": [bucket("2026-07-02", {})], "has_more": False}

    buckets = api_client.fetch_cost_buckets(
        "2026-07-01T00:00:00Z", "2026-07-03T00:00:00Z", fetcher=fake_fetch
    )
    assert len(buckets) == 2 and len(calls) == 2
    for url, headers in calls:
        assert headers["x-api-key"] == FAKE_KEY
        assert headers["anthropic-version"] == api_client.ANTHROPIC_VERSION
        assert url.startswith(api_client.API_BASE + api_client.COST_REPORT_PATH)
        assert "bucket_width=1d" in url
    assert "page=p2" in calls[1][0]


def test_missing_key_raises_without_leaking(monkeypatch):
    monkeypatch.delenv(api_client.ADMIN_KEY_ENV_VAR, raising=False)
    with pytest.raises(api_client.MissingAdminKeyError) as excinfo:
        api_client.fetch_cost_buckets("2026-07-01T00:00:00Z", "2026-07-02T00:00:00Z")
    assert "sk-ant" not in str(excinfo.value)


def test_pagination_error_surfaces(monkeypatch):
    monkeypatch.setenv(api_client.ADMIN_KEY_ENV_VAR, FAKE_KEY)

    def bad_fetch(url: str, headers: dict) -> dict:
        return {"data": [], "has_more": True}  # no next_page

    with pytest.raises(api_client.ApiError, match="next_page"):
        api_client.fetch_cost_buckets("x", "y", fetcher=bad_fetch)


def test_reconcile_cli_with_mocked_api(monkeypatch, capsys):
    """Integration: fixture 1 reconciles within 2% against a matching mock."""
    monkeypatch.setenv(api_client.ADMIN_KEY_ENV_VAR, FAKE_KEY)

    def fake_buckets(starting_at: str, ending_at: str, fetcher=None) -> list[dict]:
        assert starting_at == "2026-07-01T00:00:00Z"
        return [
            bucket(
                "2026-07-01",
                {
                    "uncached_input_tokens": str(F1_INPUT),
                    "cache_creation.ephemeral_5m_input_tokens": "0.0421875",
                    "cache_creation.ephemeral_1h_input_tokens": "0.012",
                    "cache_read_input_tokens": str(F1_CACHE_READ),
                    "output_tokens": "0.02",  # API ground truth differs: still estimated-only
                },
            )
        ]

    monkeypatch.setattr(api_client, "fetch_cost_buckets", fake_buckets)
    code = cli.main(
        [
            "reconcile",
            str(GOLDEN / "01-simple-session"),
            "--pricing-dir",
            str(PRICING),
            "--snapshot",
            "2026-07",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("within_tolerance") == 3  # input, cache_write, cache_read
    assert "estimated_output" in out
    assert "[OK]" in out and "INVESTIGATE" not in out
    assert "target: within 2% per stream" in out
    assert FAKE_KEY not in out  # invariant 3: key never printed


def test_reconcile_cli_missing_key(monkeypatch, capsys):
    monkeypatch.delenv(api_client.ADMIN_KEY_ENV_VAR, raising=False)
    code = cli.main(
        [
            "reconcile",
            str(GOLDEN / "01-simple-session"),
            "--pricing-dir",
            str(PRICING),
        ]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert api_client.ADMIN_KEY_ENV_VAR in out
