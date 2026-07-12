# Issue 10 — Insight lab queries

## Goal
DuckDB layer over canonical events (`lab/events.duckdb`, rebuilt by
`make lab`). Saved queries in `lab/queries/` for the Week-1 experiments:

- **Q1** — session cache-health distribution + share below 85%
- **Q2** — bust trigger table
- **Q3** — reconciliation divergence by day
- **Q4** — task-type spend shares
- **Q5** — fan-out multiplier distribution
- **Q6** — $ recoverable per prescription

Plus a markdown insight-notebook template in `lab/notebooks/`.

## Acceptance criteria
- `make lab` produces all six query outputs from the corpus.
- Results feed directly into the go/no-go thresholds: > 30% of sessions below
  85% health ⇒ bust thesis has legs; < 5% recoverable ⇒ pivot signal.

## Human gate
None (but insights get dated notes in `lab/notebooks/` — surprises are
product).

## Dependencies
Issues 2–8. Individual queries can start as soon as their inputs exist.
