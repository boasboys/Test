# tokenlens — Agent Rules

## Mission
Free, local-first analyzer for Claude Code spend: correct token accounting,
cache forensics, task-type attribution, invoice reconciliation.
Read docs/spec.md before any work.

## Hard invariants (violating these fails review)
1. NEVER modify: tests/fixtures/golden/*, pricing/*.yaml, src/tokenlens/pricing/engine.py,
   src/tokenlens/reconcile/tieout.py — propose changes in the PR description instead.
2. No network calls anywhere except src/tokenlens/reconcile/api_client.py.
3. No secrets in code or logs. Admin key only via env var, never printed.
4. Every $ figure must carry a pricing-snapshot ID. Unknown model = raise, never $0.
5. Dedup is last-wins by (message_id, request_id). Do not "simplify" this.
6. All parsing must survive malformed lines: skip, count, report — never crash.

## Workflow
- Test-first: write failing acceptance tests from the issue file, then implement.
- Run `make test` before claiming done. Paste the output in your summary.
- Small PRs: one issue = one branch = one PR. Do not drift into other issues.
- If the issue spec is ambiguous, STOP and write questions in the PR — do not guess
  on anything touching money, dedup, or fixtures.

## Style
Python 3.12, typed, ruff clean. No new dependencies without listing them
in the PR description with a one-line justification.
