# Pricing snapshots — LOAD-BEARING

Dated snapshots of Anthropic model pricing, one file per month of validity:
`2026-07.yaml`, `2026-08.yaml`, …

Rules (CLAUDE.md invariants 1 and 4):

- **Agents never edit these files.** Changes are proposed in PR descriptions
  and applied by a human after hand-verification against Anthropic's pricing
  page. CI rejects PRs that touch `pricing/*.yaml` without the
  `fixture-change-approved` label.
- Snapshots are **append-only**: a price change means a *new* dated file,
  never an edit to an old one — historical costs must stay reproducible.
- Every snapshot records: per-model input/output $/MTok, cache-write
  multipliers (1.25× for 5m, 2× for 1h), cache-read multiplier (0.1×), and
  any batch / inference_geo / long-context multipliers, plus the source URL
  and verification date.
- The first snapshot lands with Issue 3 (docs/issues/issue-03.md), seeded from
  the LiteLLM table and hand-verified before merge.
