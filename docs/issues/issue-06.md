# Issue 6 — ∥ Task-type classifier: `tokenlens tasks`

## Goal
Deterministic turn classification (CodeBurn-style): conversation (no tool
calls), exploration (Read/Grep/Glob-dominant), coding (Edit/Write), debugging
(Edit→Bash→Edit retry pattern), testing, git ops, build/deploy, planning,
delegation (sub-agent spawn), general. Spend by category; one-shot rate per
category.

## Acceptance criteria
- Hand-labeled 50-turn fixture reaches ≥ 90% agreement (add the fixture under
  `tests/fixtures/` — new fixtures are allowed; modifying golden ones is not).
- Category shares sum to 100%.
- Corpus report shows conversation% and exploration% (compare against the
  25–56% and ~47% benchmarks).

## Human gate
Human hand-labels the 50-turn fixture (labels are ground truth; agents don't
author them).

## Dependencies
Issues 2, 3. Parallel-safe with 3, 4, 7, 8-connector.
