"""Cache forensics v1 — health scores and bust detection (Issue 4).

Operates on CORRECTED (deduped) events for one session, ordered by timestamp.
Turn numbers are 1-based positions in that order.
"""

from __future__ import annotations

from dataclasses import dataclass

from tokenlens.ingest.parser import Event

# A session at >= HEALTHY_THRESHOLD reads most of its context from cache;
# >= EXCELLENT_THRESHOLD is what a stable long session should sustain.
HEALTHY_THRESHOLD = 0.85
EXCELLENT_THRESHOLD = 0.92

# Regression signature: cache_read staying flat (within this relative band)
# while cache_creation keeps growing for >= REGRESSION_MIN_TURNS turns.
REGRESSION_READ_BAND = 0.05
REGRESSION_MIN_TURNS = 3


@dataclass(frozen=True, slots=True)
class BustEvent:
    """One detected cache bust within a session."""

    session_id: str
    turn: int  # 1-based position among the session's corrected events
    message_id: str
    timestamp: str
    kind: str  # read_drop | creation_dominant | regression


def cache_health(events: list[Event]) -> float | None:
    """cache_read / (cache_read + cache_creation + input) over a session.

    None when the session moved no input-side tokens at all.
    """
    read = sum(e.cache_read_tokens for e in events)
    creation = sum(e.cache_creation_tokens for e in events)
    inp = sum(e.input_tokens for e in events)
    denominator = read + creation + inp
    if denominator == 0:
        return None
    return read / denominator


def _ordered(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: e.timestamp)


def detect_busts(events: list[Event]) -> list[BustEvent]:
    """Find cache busts in one session's corrected events.

    At most one bust per turn; the first turn never busts (nothing is cached
    yet — that cost is expected). Detection signatures, in precedence order:

    - read_drop: cache_read fell to 0 on a non-first turn.
    - creation_dominant: cache_creation > cache_read on a non-first turn.
    - regression: cache_read flat while cache_creation grows for >= 3 turns.
    """
    ordered = _ordered(events)
    busts: list[BustEvent] = []
    busted_turns: set[int] = set()

    for turn, event in enumerate(ordered[1:], start=2):
        kind: str | None = None
        if event.cache_read_tokens == 0:
            kind = "read_drop"
        elif event.cache_creation_tokens > event.cache_read_tokens:
            kind = "creation_dominant"
        if kind is not None:
            busts.append(
                BustEvent(
                    session_id=event.session_id,
                    turn=turn,
                    message_id=event.message_id,
                    timestamp=event.timestamp,
                    kind=kind,
                )
            )
            busted_turns.add(turn)

    busts.extend(_detect_regressions(ordered, busted_turns))
    return sorted(busts, key=lambda b: b.turn)


def _detect_regressions(ordered: list[Event], busted_turns: set[int]) -> list[BustEvent]:
    """Flag runs of >= REGRESSION_MIN_TURNS turns with flat read + growing creation."""
    regressions: list[BustEvent] = []
    run_start: int | None = None  # 1-based turn index of the run's first event

    def run_length(current_turn: int) -> int:
        return 0 if run_start is None else current_turn - run_start + 1

    def flush(end_turn: int) -> None:
        if run_start is not None and run_length(end_turn) >= REGRESSION_MIN_TURNS:
            event = ordered[run_start - 1]
            regressions.append(
                BustEvent(
                    session_id=event.session_id,
                    turn=run_start,
                    message_id=event.message_id,
                    timestamp=event.timestamp,
                    kind="regression",
                )
            )

    for turn in range(2, len(ordered) + 1):
        prev, curr = ordered[turn - 2], ordered[turn - 1]
        growing = curr.cache_creation_tokens > prev.cache_creation_tokens > 0
        base = max(prev.cache_read_tokens, 1)
        flat = abs(curr.cache_read_tokens - prev.cache_read_tokens) / base <= REGRESSION_READ_BAND
        clean = turn not in busted_turns and (turn - 1) not in busted_turns
        if growing and flat and clean:
            if run_start is None:
                run_start = turn - 1
        else:
            flush(turn - 1)
            run_start = None
    flush(len(ordered))
    return regressions
