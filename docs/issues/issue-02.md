# Issue 2 — Correct token accounting (the load-bearing slice)

## Goal
Dedup by `(message.id, requestId)`, **last-wins** — streaming duplicates write
2–10 entries with growing `output_tokens`. Flag `output_tokens` as
placeholder-unreliable; keep raw and corrected columns. Establish the canonical
event schema (one row per API call: session, lineage fields, 4 token streams +
5m/1h cache split, model, version, timestamp) — see `docs/spec.md` §1.

## Acceptance criteria
- Fixture 2 (`02-streaming-duplicates`) dedups to exactly the known N events
  in its `expected.json`.
- Property test: dedup is idempotent (dedup(dedup(x)) == dedup(x)).
- Corrected totals ≤ raw totals, per stream.
- Corpus-wide dedup rate reported.

## Human gate
**REVIEW REQUIRED** — this logic underpins every dollar claim. The human reads
the dedup diff line by line before merge.

## Dependencies
Issue 1.
