"""JSONL parsing into canonical events (Issues 1, 2).

One ``Event`` per usage-bearing JSONL line. Streaming writes 2-10 lines per
API call, so pre-dedup event lists overcount; Issue 2's last-wins dedup in
``accounting.py`` corrects this. Parsing never crashes on malformed lines:
skip, count, report (CLAUDE.md invariant 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

STREAMS: tuple[str, ...] = (
    "input_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "output_tokens",
)


@dataclass(frozen=True, slots=True)
class Event:
    """One usage-bearing JSONL entry — pre-dedup, one per streaming write.

    ``output_tokens`` is a streaming placeholder and must be treated as an
    estimate, never authoritative (docs/spec.md §1-2).
    """

    session_id: str
    event_uuid: str
    parent_uuid: str | None
    is_sidechain: bool
    agent_id: str | None
    message_id: str
    request_id: str
    model: str
    version: str
    timestamp: str  # ISO-8601 UTC as written; lexicographically sortable
    input_tokens: int
    cache_creation_tokens: int
    cache_creation_5m: int
    cache_creation_1h: int
    cache_read_tokens: int
    output_tokens: int
    service_tier: str
    content_types: tuple[str, ...]
    tool_names: tuple[str, ...]
    tool_use_ids: tuple[str, ...]
    # First 3 whitespace tokens of each Bash tool_use command, lowercased —
    # enough to classify testing/git/build turns (Issue 6) without keeping
    # full command lines. Absent in anonymized corpora (inputs stripped).
    bash_commands: tuple[str, ...]
    source_file: str

    @property
    def dedup_key(self) -> tuple[str, str]:
        """Invariant 5: dedup is last-wins by (message_id, request_id)."""
        return (self.message_id, self.request_id)

    def stream(self, name: str) -> int:
        return int(getattr(self, name))


@dataclass(slots=True)
class SessionMeta:
    """Per-session lineage metadata gathered from ALL lines, including user
    lines — parentToolUseId typically appears only on a sidechain's first
    user entry, never on a usage-bearing assistant line (Issue 7)."""

    session_id: str
    is_sidechain: bool = False
    agent_id: str | None = None
    parent_tool_use_id: str | None = None
    # Bust-attribution evidence (Issue 5) — timestamps of lines carrying an
    # image content block / a compact marker. Images usually arrive in user
    # or tool_result lines, never in usage-bearing assistant lines.
    image_timestamps: list[str] = field(default_factory=list)
    compact_timestamps: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanResult:
    """All events under a directory plus parse bookkeeping."""

    events: list[Event]
    files_scanned: int
    lines_total: int
    malformed_lines: int
    session_meta: dict[str, SessionMeta]


def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _event_from_entry(entry: dict, source_file: str) -> Event | None:
    """Build an Event from a parsed JSONL entry; None if not usage-bearing."""
    if entry.get("type") != "assistant":
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    cache_creation = _int(usage.get("cache_creation_input_tokens"))
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        cc_5m = _int(split.get("ephemeral_5m_input_tokens"))
        cc_1h = _int(split.get("ephemeral_1h_input_tokens"))
    else:
        # Older Claude Code versions omit the split; 5m is the default TTL.
        cc_5m, cc_1h = cache_creation, 0

    content_types: list[str] = []
    tool_names: list[str] = []
    tool_use_ids: list[str] = []
    bash_commands: list[str] = []
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "unknown"))
            content_types.append(block_type)
            if block_type in ("tool_use", "server_tool_use"):
                if block.get("name"):
                    tool_names.append(str(block["name"]))
                if block.get("id"):
                    tool_use_ids.append(str(block["id"]))
                if block.get("name") == "Bash":
                    block_input = block.get("input")
                    command = (
                        block_input.get("command") if isinstance(block_input, dict) else None
                    )
                    if isinstance(command, str) and command.strip():
                        head = " ".join(command.strip().lower().split()[:3])
                        bash_commands.append(head)

    uuid = str(entry.get("uuid") or "")
    return Event(
        session_id=str(entry.get("sessionId") or ""),
        event_uuid=uuid,
        parent_uuid=entry.get("parentUuid"),
        is_sidechain=bool(entry.get("isSidechain")),
        agent_id=entry.get("agentId"),
        # Surrogate to the line uuid when ids are absent so unrelated events
        # never collapse into one dedup key.
        message_id=str(message.get("id") or uuid),
        request_id=str(entry.get("requestId") or uuid),
        model=str(message.get("model") or "unknown"),
        version=str(entry.get("version") or "unknown"),
        timestamp=str(entry.get("timestamp") or ""),
        input_tokens=_int(usage.get("input_tokens")),
        cache_creation_tokens=cache_creation,
        cache_creation_5m=cc_5m,
        cache_creation_1h=cc_1h,
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        service_tier=str(usage.get("service_tier") or "standard"),
        content_types=tuple(content_types),
        tool_names=tuple(tool_names),
        tool_use_ids=tuple(tool_use_ids),
        bash_commands=tuple(bash_commands),
        source_file=source_file,
    )


def _contains_image(content: object) -> bool:
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            return True
        if block.get("type") == "tool_result" and _contains_image(block.get("content")):
            return True
    return False


def _update_meta(meta: dict[str, SessionMeta], entry: dict) -> None:
    session_id = entry.get("sessionId")
    if not session_id:
        return
    record = meta.setdefault(str(session_id), SessionMeta(session_id=str(session_id)))
    if entry.get("isSidechain"):
        record.is_sidechain = True
    if record.agent_id is None and entry.get("agentId"):
        record.agent_id = str(entry["agentId"])
    if record.parent_tool_use_id is None and entry.get("parentToolUseId"):
        record.parent_tool_use_id = str(entry["parentToolUseId"])
    timestamp = str(entry.get("timestamp") or "")
    if timestamp:
        message = entry.get("message")
        if isinstance(message, dict) and _contains_image(message.get("content")):
            record.image_timestamps.append(timestamp)
        if entry.get("isCompactSummary") or entry.get("subtype") == "compact_boundary":
            record.compact_timestamps.append(timestamp)


def parse_file(
    path: Path, meta: dict[str, SessionMeta] | None = None
) -> tuple[list[Event], int, int]:
    """Parse one JSONL file. Returns (events, lines_total, malformed_lines).

    When ``meta`` is given, per-session lineage metadata is accumulated into
    it from every parseable line (not just usage-bearing ones).
    """
    events: list[Event] = []
    lines_total = malformed = 0
    with path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            lines_total += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(entry, dict):
                malformed += 1
                continue
            if meta is not None:
                _update_meta(meta, entry)
            event = _event_from_entry(entry, str(path))
            if event is not None:
                events.append(event)
    return events, lines_total, malformed


def parse_dir(root: Path) -> ScanResult:
    """Parse every *.jsonl under root (recursive), in stable sorted order."""
    result = ScanResult(
        events=[], files_scanned=0, lines_total=0, malformed_lines=0, session_meta={}
    )
    for path in sorted(root.rglob("*.jsonl")):
        events, lines_total, malformed = parse_file(path, result.session_meta)
        result.events.extend(events)
        result.files_scanned += 1
        result.lines_total += lines_total
        result.malformed_lines += malformed
    return result
