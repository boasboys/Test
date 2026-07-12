"""UTC-aligned daily tie-out of JSONL dollars vs API buckets — LOAD-BEARING.

Implemented by Issue 8 (docs/issues/issue-08.md). Once merged, agents must
not edit this file directly; propose changes in the PR description instead.

Contract:
- Days align in UTC on both sides. JSONL events bucket by the UTC date of
  their timestamp; API buckets by the UTC date of `starting_at`.
- Reconcilable streams are input / cache_write / cache_read. output is
  NEVER reconciled — JSONL output_tokens are streaming placeholders, so
  output rows are reported as estimated only, and total cost treats the
  API as ground truth.
- Every gap lands in the ledger with a classification (below) — a
  divergence is never silently dropped.

ASSUMPTION TO VERIFY DURING THE HUMAN-GATE REAL-ACCOUNT RUN: cost-report
`amount` values are decimal strings in USD dollars (not cents). If the
real account shows a consistent ~100x divergence, this is why.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from tokenlens.ingest.parser import Event, parse_timestamp
from tokenlens.pricing.engine import Snapshot, cost_event

TOLERANCE = Decimal("0.02")  # 2% acceptance threshold per day per stream

RECONCILABLE_STREAMS = ("input", "cache_write", "cache_read")
ALL_STREAMS = (*RECONCILABLE_STREAMS, "output")

# Cost-report token_type -> our stream names.
_API_STREAM_MAP = {
    "uncached_input_tokens": "input",
    "cache_creation.ephemeral_5m_input_tokens": "cache_write",
    "cache_creation.ephemeral_1h_input_tokens": "cache_write",
    "cache_read_input_tokens": "cache_read",
    "output_tokens": "output",
}

CLASSIFICATIONS = (
    "within_tolerance",
    "jsonl_above_api",  # local overcount: suspect dedup or the pricing snapshot
    "jsonl_below_api",  # usage not in local JSONL (other machines) or attribution gap
    "jsonl_only",  # API shows nothing for a day the JSONL has spend
    "api_only",  # spend on the account with no local transcript at all
    "estimated_output",  # informational: output is never reconciled
)

DayStream = tuple[str, str]  # (YYYY-MM-DD, stream)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    date: str
    stream: str
    jsonl_usd: Decimal
    api_usd: Decimal
    divergence: Decimal | None  # (jsonl-api)/api; None when api side is 0
    classification: str
    note: str


def jsonl_daily_dollars(
    events: list[Event], snapshot: Snapshot
) -> dict[DayStream, Decimal]:
    """Aggregate CORRECTED events into per-UTC-day per-stream dollars."""
    daily: dict[DayStream, Decimal] = {}

    def add(date: str, stream: str, usd: Decimal) -> None:
        daily[(date, stream)] = daily.get((date, stream), Decimal(0)) + usd

    for event in events:
        date = parse_timestamp(event.timestamp).date().isoformat()
        cost = cost_event(event, snapshot)
        add(date, "input", cost.input_usd)
        add(date, "cache_write", cost.cache_write_usd)
        add(date, "cache_read", cost.cache_read_usd)
        add(date, "output", cost.output_usd_estimated)
    return daily


def normalize_api_buckets(buckets: list[dict]) -> dict[DayStream, Decimal]:
    """Flatten raw cost-report buckets into per-UTC-day per-stream dollars.

    Unknown token_types are ignored (they belong to non-token cost types);
    unparseable amounts raise — bad money data must never pass silently.
    """
    daily: dict[DayStream, Decimal] = {}
    for bucket in buckets:
        starting_at = str(bucket.get("starting_at", ""))
        date = starting_at[:10]
        for result in bucket.get("results", []) or []:
            if not isinstance(result, dict):
                continue
            stream = _API_STREAM_MAP.get(str(result.get("token_type")))
            if stream is None:
                continue
            raw_amount = result.get("amount")
            try:
                amount = Decimal(str(raw_amount))
            except InvalidOperation as exc:
                raise ValueError(
                    f"unparseable cost-report amount {raw_amount!r} on {date}"
                ) from exc
            key = (date, stream)
            daily[key] = daily.get(key, Decimal(0)) + amount
    return daily


def _classify(jsonl_usd: Decimal, api_usd: Decimal, tolerance: Decimal) -> tuple[str, str]:
    if api_usd == 0 and jsonl_usd == 0:
        return "within_tolerance", "both sides zero"
    if api_usd == 0:
        return "jsonl_only", "API shows no spend — check account/workspace scoping"
    if jsonl_usd == 0:
        return "api_only", "no local transcript — other machines/sessions (irreducible)"
    divergence = (jsonl_usd - api_usd) / api_usd
    if abs(divergence) <= tolerance:
        return "within_tolerance", ""
    if divergence > 0:
        return "jsonl_above_api", "local overcount — suspect dedup or pricing snapshot"
    return "jsonl_below_api", "local undercount — missing transcripts or attribution gap"


def tie_out(
    jsonl_daily: dict[DayStream, Decimal],
    api_daily: dict[DayStream, Decimal],
    tolerance: Decimal = TOLERANCE,
) -> list[LedgerEntry]:
    """Compare the two sides day by day, stream by stream.

    Returns a ledger entry for every (day, stream) either side mentions —
    reconcilable streams are classified; output rows are informational.
    """
    dates = sorted({date for date, _ in (*jsonl_daily, *api_daily)})
    ledger: list[LedgerEntry] = []
    for date in dates:
        for stream in ALL_STREAMS:
            jsonl_usd = jsonl_daily.get((date, stream), Decimal(0))
            api_usd = api_daily.get((date, stream), Decimal(0))
            if jsonl_usd == 0 and api_usd == 0:
                continue
            if stream == "output":
                classification, note = (
                    "estimated_output",
                    "output_tokens are placeholders; API is ground truth for total cost",
                )
                divergence = None
            else:
                classification, note = _classify(jsonl_usd, api_usd, tolerance)
                divergence = (jsonl_usd - api_usd) / api_usd if api_usd else None
            ledger.append(
                LedgerEntry(
                    date=date,
                    stream=stream,
                    jsonl_usd=jsonl_usd,
                    api_usd=api_usd,
                    divergence=divergence,
                    classification=classification,
                    note=note,
                )
            )
    return ledger
