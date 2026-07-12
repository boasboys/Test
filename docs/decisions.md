# Decision log (append-only)

Human decisions only. Agents read this file; they never write to it.

---

## D-001 — 2026-07-12 — Bootstrap decisions (Issue 0)

- **Language/runtime:** Python, `requires-python >= 3.11`. Style target is 3.12
  (per CLAUDE.md); CI pins 3.12. Local dev containers may run 3.11 — code must
  stay compatible with both until 3.11 support is explicitly dropped.
- **Golden fixtures are synthetic at bootstrap.** The 5 fixtures in
  `tests/fixtures/golden/` were hand-authored to encode the known failure modes
  (streaming duplicates, model switch, sub-agent lineage, version upgrade) with
  hand-computed expected totals in each `expected.json`. Replacing any of them
  with anonymized real-corpus sessions requires human sign-off (they are
  load-bearing per CLAUDE.md invariant 1).
- **No pricing YAML committed yet.** `pricing/` ships with a README describing
  the snapshot process. The first dated snapshot lands with Issue 3 and must be
  hand-verified against Anthropic's pricing page before merge (human gate).
- **Dedup key is `(message.id, requestId)`, last-wins.** Encoded in CLAUDE.md
  invariant 5 and enforced by the fixture-integrity tests from day one.
- **CI fixture guard:** PRs that modify/delete golden fixtures, pricing
  snapshots, or the load-bearing modules fail CI unless the PR carries the
  `fixture-change-approved` label (applied by a human).
