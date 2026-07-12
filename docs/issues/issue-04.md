# Issue 4 — ∥ Cache forensics v1: `tokenlens cache`

## Goal
Per-session cache-health score:
`cache_read / (cache_read + cache_creation + input)`.
Bust-event detection: `cache_read → 0` mid-session; `cache_creation >
cache_read` on non-first turns; regression signature (flat read + growing
creation ≥ 3 turns). Fleet histogram of session scores with 85% / 92%
reference lines.

## Acceptance criteria
- Fixture 3 (`03-model-switch`) yields **exactly 1** bust event at the known
  turn (see its `expected.json`).
- A healthy fixture (fixture 1) yields 0 bust events.
- Histogram renders on the corpus.

## Human gate
None (attribution heuristics are reviewed in Issue 5).

## Dependencies
Issue 2. Parallel-safe with 3, 6, 7, 8-connector.
