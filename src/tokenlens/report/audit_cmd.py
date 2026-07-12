"""`tokenlens audit` — the one-command shareable report (Issue 9).

Markdown output composed from the other components; every dollar figure is
traceable: costs carry the pricing snapshot ID, bust damages come from the
Issue 5 attribution ledger, and output-token dollars are always marked
estimated. Anonymized by default: session IDs are truncated to 8 chars.
Reconciliation state is reported honestly — this command works offline and
says so, pointing at `tokenlens reconcile` for the API tie-out.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from tokenlens.classify.turns import classify_sessions
from tokenlens.forensics.attribution import TRIGGERS, attribute_all, unknown_rate
from tokenlens.forensics.health import HEALTHY_THRESHOLD, cache_health
from tokenlens.ingest.accounting import dedup_last_wins, dedup_rate
from tokenlens.ingest.lineage import build_families, fan_out
from tokenlens.ingest.parser import Event, ScanResult, parse_dir
from tokenlens.pricing.engine import (
    Snapshot,
    SnapshotError,
    UnknownModelError,
    cost_event,
    latest_snapshot,
    load_snapshot,
)

_PRESCRIPTIONS = {
    "model_change": "Pin a single model per session — mid-session switches re-pay the prefix",
    "version_change": "Restart sessions after Claude Code upgrades — version changes bust caches",
    "ttl_gap": "Keep sessions warm: gaps over 5 minutes expire the 5-minute cache TTL",
    "image": "Attach images early — images entering mid-session invalidate the cached prefix",
    "compact": "Tune compaction triggers — each compact rebuilds the context from scratch",
    "unknown": "Investigate unattributed busts (unknown trigger)",
}


def _anon(session_id: str) -> str:
    return session_id[:8]


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_audit(result: ScanResult, snapshot: Snapshot) -> str:
    corrected = dedup_last_wins(result.events)
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in corrected:
        by_session[event.session_id].append(event)

    md: list[str] = ["# tokenlens audit", ""]

    # -- corpus + accounting ------------------------------------------------
    rate = dedup_rate(len(result.events), len(corrected))
    md += [
        "## Corpus",
        "",
        f"- files: {result.files_scanned}, lines: {result.lines_total}, "
        f"malformed skipped: {result.malformed_lines}",
        f"- sessions: {len(by_session)}, events: {len(result.events)} raw → "
        f"{len(corrected)} corrected (dedup rate {rate:.1%}, last-wins by "
        "message_id+request_id)",
        "",
    ]

    # -- spend ---------------------------------------------------------------
    costs = [cost_event(e, snapshot) for e in corrected]
    input_usd = sum((c.input_usd for c in costs), Decimal(0))
    write_usd = sum((c.cache_write_usd for c in costs), Decimal(0))
    read_usd = sum((c.cache_read_usd for c in costs), Decimal(0))
    output_usd = sum((c.output_usd_estimated for c in costs), Decimal(0))
    total_usd = input_usd + write_usd + read_usd + output_usd
    verified_note = "" if snapshot.verified else " — **UNVERIFIED, human gate pending**"
    md += [
        f"## Spend (pricing snapshot `{snapshot.snapshot_id}`{verified_note})",
        "",
        *_md_table(
            ["stream", "usd"],
            [
                ["input", f"${input_usd:.4f}"],
                ["cache write", f"${write_usd:.4f}"],
                ["cache read", f"${read_usd:.4f}"],
                ["output (estimated)", f"${output_usd:.4f}"],
                ["**total**", f"**${total_usd:.4f}**"],
            ],
        ),
        "",
        "Unreconciled (JSONL-derived): run `tokenlens reconcile` with an admin key "
        "to tie these dollars out against the Cost API.",
        "",
    ]

    # -- cache health ---------------------------------------------------------
    scores = {
        sid: score
        for sid, events in by_session.items()
        if (score := cache_health(events)) is not None
    }
    below = sorted(
        ((sid, s) for sid, s in scores.items() if s < HEALTHY_THRESHOLD),
        key=lambda kv: kv[1],
    )
    md += [
        "## Cache health",
        "",
        f"- sessions below {HEALTHY_THRESHOLD:.0%} health: {len(below)}/{len(scores)}",
        "",
        *_md_table(
            ["session", "health"],
            [[_anon(sid), f"{score:.1%}"] for sid, score in below],
        ),
        "",
    ]

    # -- bust triggers ---------------------------------------------------------
    attributions = attribute_all(result, snapshot)
    trigger_rows: list[list[str]] = []
    damage_by_trigger: dict[str, Decimal] = {}
    for trigger in TRIGGERS:
        matching = [a for a in attributions if a.trigger == trigger]
        if not matching:
            continue
        damage = sum((a.damage_usd for a in matching), Decimal(0))
        damage_by_trigger[trigger] = damage
        trigger_rows.append([trigger, str(len(matching)), f"${damage:.4f}"])
    md += [
        "## Bust triggers",
        "",
        *(
            _md_table(["trigger", "busts", "damage"], trigger_rows)
            if trigger_rows
            else ["No cache busts detected."]
        ),
        "",
        f"Unknown-trigger rate: {unknown_rate(attributions):.0%}.",
        "",
    ]

    # -- task types --------------------------------------------------------------
    categories, stats = classify_sessions(corrected)
    spend_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for event, cost in zip(corrected, costs, strict=True):
        spend_by_category[categories[event.event_uuid]] += cost.total_usd
    total_turns = sum(s.turns for s in stats.values())
    task_rows = [
        [
            category,
            str(s.turns),
            f"{s.turns / total_turns:.1%}",
            f"${spend_by_category[category]:.4f}",
        ]
        for category, s in stats.items()
        if s.turns
    ]
    md += [
        "## Task types",
        "",
        *_md_table(["category", "turns", "share", "spend"], task_rows),
        "",
        f"Conversation ${spend_by_category['conversation']:.4f} + exploration "
        f"${spend_by_category['exploration']:.4f} are the waste-review candidates.",
        "",
    ]

    # -- fan-out --------------------------------------------------------------
    families = [fan_out(f) for f in build_families(result)]
    spawning = [f for f in families if f.subagent_count > 0]
    md += [
        "## Sub-agent fan-out",
        "",
        f"- families: {len(families)}, with sub-agents: {len(spawning)}, "
        f"max fan-out: {max((f.subagent_count for f in families), default=0)}",
        *(
            [
                f"- {_anon(f.root_session)}: {f.subagent_count} sub-agent(s), "
                f"{f.subagent_share:.1%} of family tokens, haiku share {f.haiku_share:.0%}"
                for f in spawning
            ]
        ),
        "",
    ]

    # -- prescriptions ----------------------------------------------------------
    ranked = sorted(damage_by_trigger.items(), key=lambda kv: kv[1], reverse=True)[:5]
    md += ["## Top prescriptions by recoverable $", ""]
    if ranked:
        md += [
            f"{i}. **${damage:.4f}** — {_PRESCRIPTIONS[trigger]} "
            f"(`{trigger}`, snapshot `{snapshot.snapshot_id}`)"
            for i, (trigger, damage) in enumerate(ranked, start=1)
        ]
    else:
        md += ["No recoverable bust damage found — cache behavior looks healthy."]
    md += [
        "",
        "---",
        "Session IDs are truncated (anonymized-by-default). Output-token dollars are "
        "estimates; every figure carries pricing snapshot "
        f"`{snapshot.snapshot_id}`.",
    ]
    return "\n".join(md) + "\n"


def run(
    path: Path,
    pricing_dir: Path,
    snapshot_id: str | None = None,
    out: Path | None = None,
) -> int:
    if not path.is_dir():
        print(f"tokenlens audit: not a directory: {path}")
        return 1
    try:
        snapshot = (
            load_snapshot(pricing_dir / f"{snapshot_id}.yaml")
            if snapshot_id
            else latest_snapshot(pricing_dir)
        )
        report = render_audit(parse_dir(path), snapshot)
    except (SnapshotError, UnknownModelError) as exc:
        print(f"tokenlens audit: {exc}")
        return 1
    if out is not None:
        out.write_text(report, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(report, end="")
    return 0
