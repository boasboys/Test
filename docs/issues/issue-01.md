# Issue 1 — Walking skeleton: `tokenlens scan`

## Goal
Parse every JSONL file in a directory; print a per-session table: session ID,
turns, raw token totals (4 streams), model(s), Claude Code version(s),
duration. **No dedup yet** — label output "RAW/UNCORRECTED."

## Acceptance criteria
- Runs on the full corpus without crashing.
- Handles malformed lines: skip + count (invariant 6), report the count.
- Snapshot test against golden fixture 1 (`tests/fixtures/golden/01-simple-session`).

## Human gate
None.

## Dependencies
Issue 0.
