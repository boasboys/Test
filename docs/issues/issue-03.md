# Issue 3 — ∥ Pricing engine: `tokenlens cost`

## Goal
Dated pricing snapshots (`pricing/2026-07.yaml` etc.), seeded from the LiteLLM
table, pinned + hand-verified against Anthropic's pricing page. Multiplier
stack: cache write 1.25× (5m) / 2× (1h), cache read 0.1×, batch,
inference_geo, long-context. Cost per event → per session. Every output
records its pricing-snapshot ID.

## Acceptance criteria
- Unit tests with hand-computed costs for each multiplier combination.
- Unknown model → explicit error, **never silent $0** (invariant 4).
- Every emitted dollar figure carries the snapshot ID it was computed with.

## Human gate
**REVIEW REQUIRED** — human verifies 10 hand-computed cases against the
snapshot before merge. `pricing/*.yaml` and `src/tokenlens/pricing/engine.py`
are load-bearing (invariant 1): after this issue merges, agents propose changes
in PR descriptions, never edit directly.

## Dependencies
Issue 2. Parallel-safe with 4, 6, 7, 8-connector.
