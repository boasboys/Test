# Reviewer agent prompt (separate session, runs on every PR)

```
You are a hostile code reviewer for the tokenlens repo. Read CLAUDE.md,
docs/spec.md, and docs/issues/issue-NN.md, then review the diff on branch issue-NN.

Hunt specifically for:
1. Invariant violations (load-bearing files, network calls outside api_client,
   secret leakage, silent $0 on unknown models, dedup shortcuts).
2. Correctness traps from the spec: first-wins instead of last-wins dedup,
   double-counting sub-agent cache creation, missing 5m/1h split, UTC boundary
   errors in reconciliation, placeholder output_tokens treated as authoritative.
3. Tests that assert the implementation rather than the issue's acceptance criteria.
4. Security: injection via JSONL content, path traversal on corpus dirs, unsafe YAML load.
Output: BLOCKERS / CONCERNS / NITS, each with file:line. Be specific. Do not fix; only report.
```

# The daily loop

1. **Morning (human, 30 min):** pick 2–4 parallel-safe issues; create
   worktrees: `git worktree add ../tl-issue-NN issue-NN`. Log decisions in
   docs/decisions.md.
2. **Dispatch:** one Claude Code session per worktree with the implementer
   prompt. Approve/correct each plan — highest-leverage 10 minutes per issue.
3. **Midday:** collect finished branches; run the reviewer agent on each; feed
   BLOCKERS back to the implementing session.
4. **Human gate (non-delegable):** personally read every diff touching
   pricing/, reconcile/, dedup logic, and api_client — line by line.
5. **Merge & lab:** merge green branches; run `make lab` on fresh corpus;
   write one insight note if anything surprises. Surprises are product.
6. **Weekly:** re-snapshot corpus, re-run `tokenlens audit` on yourself, check
   divergence trend, prune stale worktrees.

**Budget guardrail:** implementers on Sonnet, reviewer on Opus; cap thinking
effort on implementation sessions.

**Failure-mode watchlist:** dedup "simplified" to first-wins (fixture 2
catches it); hardcoded prices (invariant 4 catches it); fixture edited to make
tests pass (CI fixture-guard = automatic reject); two agents touching shared
schema (sequence Issue 2 alone before parallelizing).
