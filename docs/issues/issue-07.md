# Issue 7 — ∥ Sub-agent lineage & fan-out

## Goal
Join parent/child sessions via `parentToolUseId` / `agentId`; resolve
cache-creation double-count; per-session fan-out metrics: sub-agent count,
sub-agent spend share, fan-out multiplier vs solo estimate; flag sub-agent
model mix (Haiku share).

## Acceptance criteria
- Fixture 4 (`04-parent-subagent`) joins correctly; no token counted twice.
- Property test: family total = sum of deduped events.
- Corpus fan-out distribution reported.

## Human gate
None.

## Dependencies
Issue 2. Parallel-safe with 3, 4, 6, 8-connector.
