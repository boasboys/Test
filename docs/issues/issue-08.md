# Issue 8 — Cost API reconciliation: `tokenlens reconcile`

## Goal
Admin Usage & Cost API connector (read-only, admin key via env var
`ANTHROPIC_ADMIN_KEY`, never logged). UTC-aligned daily tie-out: JSONL-derived
input+cache dollars vs API buckets. Divergence ledger classifying gaps (dedup?
attribution? pricing? irreducible server-side?). Output: reconciliation report
with % divergence per day per stream.

## Acceptance criteria
- Mocked-API integration tests (no live network in CI).
- On the real account: input+cache streams reconcile within 2% over a 7-day
  window — if not, the ledger explains why.
- Total cost uses the API as ground truth; JSONL output tokens marked
  estimated.
- All network I/O confined to `src/tokenlens/reconcile/api_client.py`
  (invariant 2). Key never appears in logs or output (invariant 3).

## Human gate
**REVIEW REQUIRED** — API auth handling reviewed line by line; the
real-account run is human-only. `src/tokenlens/reconcile/tieout.py` is
load-bearing (invariant 1) once merged.

## Dependencies
Issue 3 for the tie-out. The API connector itself is parallel-safe after
Issue 0.
