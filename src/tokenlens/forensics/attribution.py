"""Bust trigger attribution (Issue 5).

Classifies each detected cache bust by the evidence in the window between the
previous corrected event and the busted one, in precedence order:

1. compact        — a compact marker rebuilt the context entirely
2. model_change   — the model field changed (caches are model-scoped)
3. version_change — Claude Code upgraded (prompt prefix changed)
4. image          — an image content block entered the conversation
5. ttl_gap        — more than 5 minutes elapsed (5m cache TTL expired)
6. unknown        — none of the above; if >40% of corpus busts land here,
                    open an investigation issue (docs/issues/issue-05.md)

Damage is the Issue 3 counterfactual: what the busted turn's input-side
tokens actually cost (full-rate input + cache-write premium) minus what the
same tokens would have cost as cache reads.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from tokenlens.forensics.health import BustEvent, detect_busts
from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, ScanResult, SessionMeta, parse_timestamp
from tokenlens.pricing.engine import Snapshot, UnknownModelError

TTL_GAP = timedelta(minutes=5)
TRIGGERS = ("compact", "model_change", "version_change", "image", "ttl_gap", "unknown")
INVESTIGATE_UNKNOWN_RATE = 0.40

_MTOK = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class BustAttribution:
    bust: BustEvent
    trigger: str
    damage_usd: Decimal
    snapshot_id: str


def _damage(event: Event, snapshot: Snapshot) -> Decimal:
    """Counterfactual damage: actual input-side cost minus cached-read cost."""
    rates = snapshot.models.get(event.model)
    if rates is None:
        raise UnknownModelError(
            f"model {event.model!r} not in pricing snapshot {snapshot.snapshot_id!r} "
            f"— cannot price bust damage (never $0)"
        )
    in_rate = rates.input_per_mtok
    actual = (
        Decimal(event.input_tokens) * in_rate
        + Decimal(event.cache_creation_5m) * in_rate * snapshot.cache_write_5m
        + Decimal(event.cache_creation_1h) * in_rate * snapshot.cache_write_1h
    ) / _MTOK
    counterfactual = (
        Decimal(event.input_tokens + event.cache_creation_tokens)
        * in_rate
        * snapshot.cache_read
        / _MTOK
    )
    return actual - counterfactual


def _in_window(timestamps: list[str], start: str, end: str) -> bool:
    """True if any timestamp falls in (start, end] — after prev, up to the bust."""
    return any(start < ts <= end for ts in timestamps)


def classify_trigger(
    bust: BustEvent, ordered: list[Event], meta: SessionMeta | None
) -> str:
    curr = ordered[bust.turn - 1]
    prev = ordered[bust.turn - 2]
    if meta and _in_window(meta.compact_timestamps, prev.timestamp, curr.timestamp):
        return "compact"
    if curr.model != prev.model:
        return "model_change"
    if curr.version != prev.version:
        return "version_change"
    if meta and _in_window(meta.image_timestamps, prev.timestamp, curr.timestamp):
        return "image"
    if parse_timestamp(curr.timestamp) - parse_timestamp(prev.timestamp) > TTL_GAP:
        return "ttl_gap"
    return "unknown"


def attribute_all(result: ScanResult, snapshot: Snapshot) -> list[BustAttribution]:
    """Detect and attribute every bust across a corpus, priced per snapshot."""
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in dedup_last_wins(result.events):
        by_session[event.session_id].append(event)

    attributions: list[BustAttribution] = []
    for session_id, events in sorted(by_session.items()):
        ordered = sorted(events, key=lambda e: e.timestamp)
        meta = result.session_meta.get(session_id)
        for bust in detect_busts(ordered):
            attributions.append(
                BustAttribution(
                    bust=bust,
                    trigger=classify_trigger(bust, ordered, meta),
                    damage_usd=_damage(ordered[bust.turn - 1], snapshot),
                    snapshot_id=snapshot.snapshot_id,
                )
            )
    return attributions


def unknown_rate(attributions: list[BustAttribution]) -> float:
    if not attributions:
        return 0.0
    return sum(1 for a in attributions if a.trigger == "unknown") / len(attributions)
