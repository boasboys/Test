"""Deterministic task-type classification of turns (Issue 6).

A turn is one corrected (deduped) assistant event. Classification is purely
rule-based over the turn's tool usage — no model calls, fully reproducible.

Precedence (first match wins):
1. conversation — no tool calls at all
2. delegation   — spawns a sub-agent (Task/Agent tool)
3. debugging    — edit -> run -> edit retry pattern within the turn
4. testing      — Bash running a known test runner
5. git_ops      — Bash running git/gh
6. build_deploy — Bash running a build/deploy tool
7. coding       — Edit/Write-family tools
8. planning     — only planning tools (TodoWrite/plan mode)
9. exploration  — only read-side tools (Read/Grep/Glob/web)
10. general     — anything else (incl. unclassifiable Bash — note that
    anonymized corpora strip command text, so their Bash turns land here)

"One-shot rate" per category: within a session, consecutive same-category
turns form a run; a run of length 1 is a one-shot. rate = one-shot runs /
all runs of that category. Low rates mean repeated back-and-forth.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from tokenlens.ingest.parser import Event

CATEGORIES: tuple[str, ...] = (
    "conversation",
    "exploration",
    "coding",
    "debugging",
    "testing",
    "git_ops",
    "build_deploy",
    "planning",
    "delegation",
    "general",
)

READ_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead", "WebFetch", "WebSearch"}
CODE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
PLAN_TOOLS = {"TodoWrite", "EnterPlanMode", "ExitPlanMode", "exit_plan_mode"}
DELEGATE_TOOLS = {"Task", "Agent"}

_TEST_MARKERS = ("pytest", "jest", "vitest", "tox")
_TEST_PREFIXES = ("go test", "npm test", "yarn test", "make test", "cargo test", "bun test")
_BUILD_PREFIXES = (
    "make",
    "docker",
    "npm run build",
    "yarn build",
    "cargo build",
    "go build",
    "terraform",
    "kubectl",
    "helm",
)


def _bash_kind(command: str) -> str | None:
    """Classify one (truncated, lowercased) bash command head."""
    if any(marker in command for marker in _TEST_MARKERS) or command.startswith(
        _TEST_PREFIXES
    ):
        return "testing"
    if command.startswith(("git ", "gh ")) or command in ("git", "gh"):
        return "git_ops"
    if command.startswith(_BUILD_PREFIXES):
        return "build_deploy"
    return None


def _has_edit_run_edit(tool_names: tuple[str, ...]) -> bool:
    """edit ... Bash ... edit within one turn — the retry signature."""
    state = 0
    for name in tool_names:
        if state in (0, 2) and name in CODE_TOOLS:
            state += 1
            if state == 3:
                return True
        elif state == 1 and name == "Bash":
            state = 2
    return False


def classify_turn(event: Event) -> str:
    tools = event.tool_names
    if not tools:
        return "conversation"
    if any(name in DELEGATE_TOOLS for name in tools):
        return "delegation"
    if _has_edit_run_edit(tools):
        return "debugging"
    bash_kinds = {_bash_kind(cmd) for cmd in event.bash_commands} - {None}
    for kind in ("testing", "git_ops", "build_deploy"):
        if kind in bash_kinds:
            return kind
    if any(name in CODE_TOOLS for name in tools):
        return "coding"
    if all(name in PLAN_TOOLS for name in tools):
        return "planning"
    if all(name in READ_TOOLS for name in tools):
        return "exploration"
    return "general"


@dataclass(slots=True)
class CategoryStats:
    turns: int = 0
    one_shot_runs: int = 0
    total_runs: int = 0

    @property
    def one_shot_rate(self) -> float | None:
        if self.total_runs == 0:
            return None
        return self.one_shot_runs / self.total_runs


def classify_sessions(events: list[Event]) -> tuple[dict[str, str], dict[str, CategoryStats]]:
    """Classify corrected events; return (category per event uuid, stats).

    Run counting is per session over timestamp-ordered turns.
    """
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_session[event.session_id].append(event)

    categories: dict[str, str] = {}
    stats: dict[str, CategoryStats] = {c: CategoryStats() for c in CATEGORIES}
    for session_events in by_session.values():
        ordered = sorted(session_events, key=lambda e: e.timestamp)
        labels = [classify_turn(e) for e in ordered]
        for event, label in zip(ordered, labels, strict=True):
            categories[event.event_uuid] = label
            stats[label].turns += 1
        run_start = 0
        for i in range(1, len(labels) + 1):
            if i == len(labels) or labels[i] != labels[run_start]:
                stats[labels[run_start]].total_runs += 1
                if i - run_start == 1:
                    stats[labels[run_start]].one_shot_runs += 1
                run_start = i
    return categories, stats
