# tokenlens audit

## Corpus

- files: 6, lines: 44, malformed skipped: 1
- sessions: 6, events: 23 raw → 20 corrected (dedup rate 13.0%, last-wins by message_id+request_id)

## Spend (pricing snapshot `2026-07` — **UNVERIFIED, human gate pending**)

| stream | usd |
|---|---|
| input | $0.0005 |
| cache write | $0.6363 |
| cache read | $0.0841 |
| output (estimated) | $0.0877 |
| **total** | **$0.8086** |

Unreconciled (JSONL-derived): run `tokenlens reconcile` with an admin key to tie these dollars out against the Cost API.

## Cache health

- sessions below 85% health: 6/6

| session | health |
|---|---|
| f4000000 | 48.9% |
| f4000000 | 48.9% |
| f5000000 | 49.3% |
| f1000000 | 65.2% |
| f2000000 | 65.8% |
| f3000000 | 65.9% |

## Bust triggers

| trigger | busts | damage |
|---|---|---|
| model_change | 1 | $0.2571 |
| version_change | 1 | $0.0469 |

Unknown-trigger rate: 0%.

## Task types

| category | turns | share | spend |
|---|---|---|---|
| conversation | 19 | 95.0% | $0.7467 |
| delegation | 1 | 5.0% | $0.0618 |

Conversation $0.7467 + exploration $0.0000 are the waste-review candidates.

## Sub-agent fan-out

- families: 5, with sub-agents: 1, max fan-out: 1
- f4000000: 1 sub-agent(s), 36.2% of family tokens, haiku share 100%

## Top prescriptions by recoverable $

1. **$0.2571** — Pin a single model per session — mid-session switches re-pay the prefix (`model_change`, snapshot `2026-07`)
2. **$0.0469** — Restart sessions after Claude Code upgrades — version changes bust caches (`version_change`, snapshot `2026-07`)

---
Session IDs are truncated (anonymized-by-default). Output-token dollars are estimates; every figure carries pricing snapshot `2026-07`.
