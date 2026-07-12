# Lab queries

Saved DuckDB SQL over the canonical events table (`lab/events.duckdb`,
rebuilt by `make lab`). Lands with Issue 10 (docs/issues/issue-10.md):

- `q1_cache_health.sql` — session cache-health distribution + share below 85%
- `q2_bust_triggers.sql` — bust trigger table (count, $ damage, avg)
- `q3_divergence.sql` — reconciliation divergence by day
- `q4_task_spend.sql` — task-type spend shares
- `q5_fanout.sql` — fan-out multiplier distribution
- `q6_recoverable.sql` — $ recoverable per prescription
