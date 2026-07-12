# Issue 5 — Bust trigger attribution

## Goal
For each bust event, classify the trigger by preceding evidence: model field
change, version change, > 5-minute timestamp gap (TTL expiry), image content
block, compact marker, first-turn (expected), unknown. Price each bust via
Issue 3 counterfactual (cached-read cost vs actual). Output: trigger table —
count, total damage $, average damage per trigger.

## Acceptance criteria
- Fixtures 3 (`03-model-switch`) and 5 (`05-version-upgrade`) attribute
  correctly (model_change and version_change respectively, per their
  `expected.json`).
- Unknown-rate reported. If > 40% unknown on the corpus, open an
  investigation issue.

## Human gate
Review attribution heuristics against 10 manually inspected busts from the
real corpus before merge.

## Dependencies
Issue 4 (and Issue 3 for counterfactual pricing).
