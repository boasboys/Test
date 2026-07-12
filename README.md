# tokenlens

Free, local-first analyzer for Claude Code spend: correct token accounting,
cache forensics, task-type attribution, and invoice reconciliation — all from
the JSONL transcripts Claude Code already writes to `~/.claude/projects`.

**Status: Phase 1 bootstrap (Issue 0).** The repo scaffold, agent constitution,
issue specs, and golden fixtures are in place. The CLI commands are stubs until
their issues land — see `docs/issues/`.

## Quickstart

```sh
make test     # lint + test suite (green on the skeleton)
make corpus   # snapshot your ~/.claude/projects into lab/corpus/raw (anonymized)
make lab      # rebuild lab/events.duckdb + run insight queries (Issue 10)
make audit    # one-command shareable audit report (Issue 9)
```

## Layout

```
CLAUDE.md                  # agent constitution — read before any work
docs/spec.md               # the 10-component spec
docs/issues/               # one file per vertical issue (00–10)
docs/decisions.md          # human decision log (append-only)
src/tokenlens/             # ingest / pricing / forensics / classify / reconcile / report
pricing/                   # dated pricing snapshots  ← LOAD-BEARING
tests/fixtures/golden/     # the 5 golden fixtures    ← LOAD-BEARING
lab/                       # corpus (gitignored), queries, insight notebooks
scripts/anonymize.py       # corpus snapshot tool (strips content, keeps structure)
```

## Lab principles

- **Corpus is append-only** — re-snapshot weekly, never edit.
- **Fixtures are sacred** — agents may add, never modify without human sign-off.
- **Every insight gets a dated markdown note** in `lab/notebooks/`.

## Privacy

`scripts/anonymize.py` strips working-directory paths, git branches, and all
message content before anything enters the corpus. Only structure, usage
metadata, timestamps, and model/version fields are kept. The raw corpus is
gitignored regardless.
