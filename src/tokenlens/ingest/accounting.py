"""Correct token accounting — last-wins dedup (Issue 2). LOAD-BEARING LOGIC.

Streaming writes 2-10 JSONL entries per API call with growing output_tokens.
The corrected view keeps, for each (message_id, request_id) key, the LAST
entry seen in parse order (CLAUDE.md invariant 5 — never first-wins, never
keyed by line uuid). This underpins every dollar claim downstream.
"""

from __future__ import annotations

from tokenlens.ingest.parser import STREAMS, Event


def dedup_last_wins(events: list[Event]) -> list[Event]:
    """Collapse streaming duplicates: last entry wins per (message_id, request_id).

    Survivor order is first-seen order of each key, so output is deterministic
    and idempotent: dedup(dedup(x)) == dedup(x).
    """
    survivors: dict[tuple[str, str], Event] = {}
    for event in events:
        survivors[event.dedup_key] = event
    return list(survivors.values())


def stream_totals(events: list[Event]) -> dict[str, int]:
    """Sum of each of the 4 token streams over events."""
    return {stream: sum(e.stream(stream) for e in events) for stream in STREAMS}


def dedup_rate(raw_count: int, deduped_count: int) -> float:
    """Fraction of raw entries that were streaming duplicates, in [0, 1]."""
    if raw_count == 0:
        return 0.0
    return 1.0 - (deduped_count / raw_count)
