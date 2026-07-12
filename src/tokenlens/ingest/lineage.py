"""Sub-agent lineage & fan-out (Issue 7).

Joins parent/child sessions: a child session carries parentToolUseId (and
usually agentId / isSidechain) pointing at a Task-style tool_use block in the
spawning session. Families are built over CORRECTED (deduped) events, so no
token is ever counted twice — the family total is exactly the sum of its
deduped events.

Spend share here is measured in TOKENS across all four streams; dollar shares
land with Issue 3's pricing engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from tokenlens.ingest.accounting import dedup_last_wins
from tokenlens.ingest.parser import Event, ScanResult


@dataclass(slots=True)
class Family:
    """A root session plus every sub-agent session reachable from it."""

    root_session: str
    child_sessions: list[str]  # depth-first, root excluded
    events: list[Event]  # deduped, whole family
    orphaned: bool = False  # child pointed at a tool_use we never saw


@dataclass(frozen=True, slots=True)
class FanOut:
    root_session: str
    subagent_count: int
    family_tokens: int
    subagent_tokens: int
    subagent_share: float  # subagent_tokens / family_tokens
    fanout_multiplier: float | None  # family / root-only; None if root has 0
    haiku_share: float  # haiku tokens / subagent_tokens


def total_tokens(events: list[Event]) -> int:
    return sum(
        e.input_tokens + e.cache_creation_tokens + e.cache_read_tokens + e.output_tokens
        for e in events
    )


def _parents(result: ScanResult) -> tuple[dict[str, str], set[str]]:
    """Map child session -> parent session via parentToolUseId ownership."""
    tool_owner: dict[str, str] = {}
    for event in result.events:
        for tool_use_id in event.tool_use_ids:
            tool_owner.setdefault(tool_use_id, event.session_id)

    parent_of: dict[str, str] = {}
    orphans: set[str] = set()
    for session_id, meta in result.session_meta.items():
        if not meta.parent_tool_use_id:
            continue
        owner = tool_owner.get(meta.parent_tool_use_id)
        if owner and owner != session_id:
            parent_of[session_id] = owner
        else:
            orphans.add(session_id)
    return parent_of, orphans


def build_families(result: ScanResult) -> list[Family]:
    """Group every session with events into a family rooted at its ancestor."""
    deduped = dedup_last_wins(result.events)
    by_session: dict[str, list[Event]] = {}
    for event in deduped:
        by_session.setdefault(event.session_id, []).append(event)

    parent_of, orphans = _parents(result)

    def root_of(session_id: str) -> str:
        seen = {session_id}
        while session_id in parent_of:
            session_id = parent_of[session_id]
            if session_id in seen:  # cycle guard: treat as its own root
                break
            seen.add(session_id)
        return session_id

    members: dict[str, list[str]] = {}
    for session_id in by_session:
        members.setdefault(root_of(session_id), []).append(session_id)

    families = []
    for root, sessions in sorted(members.items()):
        children = sorted(s for s in sessions if s != root)
        events = [e for s in sessions for e in by_session[s]]
        families.append(
            Family(
                root_session=root,
                child_sessions=children,
                events=events,
                orphaned=root in orphans,
            )
        )
    return families


def fan_out(family: Family) -> FanOut:
    family_total = total_tokens(family.events)
    children = set(family.child_sessions)
    sub_events = [e for e in family.events if e.session_id in children]
    root_events = [e for e in family.events if e.session_id == family.root_session]
    sub_total = total_tokens(sub_events)
    root_total = total_tokens(root_events)
    haiku_total = total_tokens([e for e in sub_events if "haiku" in e.model])
    return FanOut(
        root_session=family.root_session,
        subagent_count=len(family.child_sessions),
        family_tokens=family_total,
        subagent_tokens=sub_total,
        subagent_share=sub_total / family_total if family_total else 0.0,
        fanout_multiplier=family_total / root_total if root_total else None,
        haiku_share=haiku_total / sub_total if sub_total else 0.0,
    )
