# Issue 0 — Lab bootstrap (do first, mostly human)

## Goal
Repo scaffold with the structure in `docs/spec.md`. Snapshot the founder's own
`~/.claude/projects` into `lab/corpus/raw/` via the anonymization script
(strips cwd paths, git branches, message content — keeps only structure +
usage metadata + timestamps + model/version fields). Create the 5 golden
fixtures. CI runs pytest + lint on every PR.

## Scope
- Repo layout per spec: `src/tokenlens/{ingest,pricing,forensics,classify,reconcile,report}`,
  `pricing/`, `tests/fixtures/golden/`, `lab/{corpus/raw,queries,notebooks}`, `docs/`.
- `CLAUDE.md` agent constitution at repo root.
- `scripts/anonymize.py` — corpus snapshot tool, wired to `make corpus`.
- 5 golden fixtures with hand-computed `expected.json` files:
  1. simple single-session
  2. session with streaming duplicates
  3. session with a model switch mid-way
  4. parent + sub-agent pair
  5. session spanning a version upgrade
- Fixture-integrity tests (recompute totals from the JSONL, compare to
  `expected.json`) so any fixture edit trips the suite.
- CI: pytest + ruff on every PR, plus a guard that rejects modifications to
  load-bearing files without human sign-off.

## Done when
- `make test` green on the empty skeleton.
- Corpus snapshot reproducible via `make corpus`.

## Human gate
Snapshotting the real corpus is human-only (it touches personal data even
post-anonymization). Everything else is scaffold.

## Dependencies
None.
