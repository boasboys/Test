# tokenlens — Phase 1 spec

Free, local-first analyzer for Claude Code spend. Input: the JSONL transcripts
Claude Code writes to `~/.claude/projects` (plus, optionally, the Anthropic
Admin Usage & Cost API for reconciliation). Output: correct token accounting,
dollar attribution, cache forensics, and a shareable audit report.

Read `CLAUDE.md` (hard invariants) before touching anything. Each component
below maps to one vertical issue in `docs/issues/`.

---

## The 10 components

### 1. Ingestion (`src/tokenlens/ingest/`) — Issues 1, 2

Parse every JSONL file under a directory. Each line is one event; lines may be
malformed (skip, count, report — never crash). The usage-bearing lines are
`type: "assistant"` entries whose `message.usage` is present; each represents
one API call (possibly duplicated by streaming, see component 2).

**Canonical event schema** — one row per API call:

| field | source |
|---|---|
| `session_id` | `sessionId` |
| `event_uuid` | `uuid` (last-wins survivor) |
| `parent_uuid` | `parentUuid` |
| `is_sidechain` / `agent_id` / `parent_tool_use_id` | lineage fields (component 7) |
| `message_id`, `request_id` | dedup key |
| `model` | `message.model` |
| `version` | Claude Code `version` |
| `timestamp` | `timestamp` (ISO-8601, UTC) |
| `input_tokens` | `message.usage.input_tokens` |
| `cache_creation_tokens` | `message.usage.cache_creation_input_tokens` |
| `cache_creation_5m` / `cache_creation_1h` | `message.usage.cache_creation.ephemeral_{5m,1h}_input_tokens` |
| `cache_read_tokens` | `message.usage.cache_read_input_tokens` |
| `output_tokens` | `message.usage.output_tokens` — **placeholder-unreliable, mark estimated** |

### 2. Correct token accounting — Issue 2 (load-bearing)

Streaming writes 2–10 JSONL entries per API call with growing `output_tokens`.
Dedup **last-wins by `(message.id, requestId)`** — never first-wins, never by
uuid. Keep raw and corrected columns side by side; report the dedup rate.
Dedup must be idempotent; corrected totals ≤ raw totals, always.

### 3. Pricing engine (`src/tokenlens/pricing/`) — Issue 3 (load-bearing)

Dated pricing snapshots in `pricing/YYYY-MM.yaml`, pinned and hand-verified.
Multiplier stack: cache write 1.25× (5m) / 2× (1h), cache read 0.1×, batch,
inference_geo, long-context. Cost per event → per session. **Every dollar
figure carries its pricing-snapshot ID. Unknown model raises — never silent $0.**

### 4. Cache forensics (`src/tokenlens/forensics/`) — Issue 4

Per-session cache-health score:
`cache_read / (cache_read + cache_creation + input)`.
Bust-event detection: `cache_read → 0` mid-session; `cache_creation >
cache_read` on non-first turns; regression signature (flat read + growing
creation for ≥ 3 turns). Fleet histogram with 85% / 92% reference lines.

### 5. Bust trigger attribution — Issue 5

Classify each bust by preceding evidence: model change, version change,
> 5-minute gap (TTL expiry), image content block, compact marker, first-turn
(expected), unknown. Price each bust as counterfactual (cached-read cost vs
actual) via component 3. Report unknown-rate; > 40% unknown ⇒ open an
investigation issue.

### 6. Task-type classifier (`src/tokenlens/classify/`) — Issue 6

Deterministic per-turn classification: conversation (no tool calls),
exploration (Read/Grep/Glob-dominant), coding (Edit/Write), debugging
(Edit→Bash→Edit retry pattern), testing, git ops, build/deploy, planning,
delegation (sub-agent spawn), general. Spend by category; one-shot rate per
category. Benchmarks to compare against: conversation 25–56%, exploration ~47%.

### 7. Sub-agent lineage — Issue 7

Join parent/child sessions via `parentToolUseId` / `agentId`. Resolve
cache-creation double-counting. Per-session fan-out metrics: sub-agent count,
sub-agent spend share, fan-out multiplier vs solo estimate, sub-agent model
mix (Haiku share). Property: family total = sum of deduped events, no token
counted twice.

### 8. Reconciliation (`src/tokenlens/reconcile/`) — Issue 8 (load-bearing)

Admin Usage & Cost API connector — read-only, admin key via env var
(`ANTHROPIC_ADMIN_KEY`), never logged. All network I/O lives in
`api_client.py` and nowhere else (invariant 2). UTC-aligned daily tie-out of
JSONL-derived input+cache dollars vs API buckets. Divergence ledger classifies
every gap (dedup? attribution? pricing? irreducible server-side?). Target:
input+cache streams within 2% over a 7-day window. Total cost uses the API as
ground truth; JSONL output tokens are marked estimated.

### 9. Audit report (`src/tokenlens/report/`) — Issue 9

The wedge feature: one command → shareable markdown/HTML report. Total spend
(reconciled), cache-health distribution + top bust triggers with $ damage,
task-type waste breakdown, fan-out summary, top 5 prescriptions ranked by
recoverable $. Anonymized-by-default share mode. Every $ figure traceable to a
component with snapshot/ledger reference.

### 10. Insight lab (`lab/`) — Issue 10

DuckDB layer over canonical events (`lab/events.duckdb`, rebuilt by
`make lab`). Six saved queries: (Q1) session cache-health distribution + share
below 85%; (Q2) bust trigger table; (Q3) reconciliation divergence by day;
(Q4) task-type spend shares; (Q5) fan-out multiplier distribution; (Q6) $
recoverable per prescription.

---

## Go / no-go thresholds (Week 1)

- **> 30%** of sessions below 85% cache health ⇒ the bust thesis has legs.
- **< 5%** of spend recoverable across prescriptions ⇒ pivot signal.

## Parallelization map

`0 → 1 → 2 → {3, 4, 6, 7, 8-connector} ∥ → 5 → 9 → 10`
(Issue 10's queries can start as soon as their inputs exist.)

## Definition of Phase 1 done

`tokenlens audit` runs on the full corpus and produces a report where every
dollar is reconciled or explained; the six lab queries answer the Week-1
go/no-go questions; the repo is clean enough to open-source on launch day.
