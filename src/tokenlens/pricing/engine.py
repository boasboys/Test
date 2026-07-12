"""Pricing engine — LOAD-BEARING (CLAUDE.md invariant 1).

Lands with Issue 3 (docs/issues/issue-03.md). Once merged, agents must not
edit this file directly; propose changes in the PR description instead.

Contract (fixed at bootstrap):
- Costs are computed from a dated snapshot in pricing/*.yaml; every dollar
  figure carries the snapshot ID it was computed with.
- An unknown model raises UnknownModelError — never a silent $0.
"""

from __future__ import annotations


class UnknownModelError(Exception):
    """Raised when an event's model has no entry in the pricing snapshot."""


def cost_event(event: dict, snapshot_id: str) -> dict:
    """Price a canonical event against the given pricing snapshot.

    Returns a dict carrying the dollar amount and the ``snapshot_id`` used.
    Raises ``UnknownModelError`` for models absent from the snapshot.
    """
    raise NotImplementedError("Issue 3 — docs/issues/issue-03.md")
