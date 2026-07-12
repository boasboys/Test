"""Minimal plain-text table rendering shared by CLI commands."""

from __future__ import annotations


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Left-aligned monospace table with a separator under the header."""
    table = [headers, *rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(headers)).rstrip(),
        "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    return "\n".join(lines)


def fmt_tokens(n: int) -> str:
    return f"{n:,}"


def fmt_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s"
