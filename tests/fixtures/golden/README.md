# Golden fixtures — SACRED (CLAUDE.md invariant 1)

Five hand-authored Claude Code JSONL sessions, each encoding one known failure
mode, with hand-computed ground truth in `expected.json`:

| fixture | encodes | key assertion |
|---|---|---|
| `01-simple-session` | healthy session + 1 malformed line + 5m/1h split | skip-and-count; totals |
| `02-streaming-duplicates` | 6 raw entries → 3 API calls | last-wins dedup by (message.id, requestId) |
| `03-model-switch` | sonnet→opus at turn 4 | exactly 1 bust, trigger `model_change` |
| `04-parent-subagent` | Task tool_use → Haiku sidechain | lineage join; family total = sum, no double count |
| `05-version-upgrade` | 1.0.44→1.0.51 at turn 3 | exactly 1 bust, trigger `version_change` |

Rules:

- **Agents may add new fixtures; they may never modify or delete these**
  without human sign-off (CI's fixture-guard rejects it without the
  `fixture-change-approved` label).
- `tests/test_fixture_integrity.py` recomputes every number in each
  `expected.json` from the raw lines — any drift fails the suite.
- These were synthetically authored at bootstrap (see docs/decisions.md
  D-001); replacing them with anonymized real-corpus sessions is a
  human-gated change.
