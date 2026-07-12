"""UTC-aligned daily tie-out of JSONL dollars vs API buckets — LOAD-BEARING.

CLAUDE.md invariant 1: once Issue 8 merges, agents must not edit this file
directly; propose changes in the PR description instead.

Contract (fixed at bootstrap):
- Days are aligned in UTC on both sides of the comparison.
- Every divergence lands in the ledger with a classification
  (dedup / attribution / pricing / irreducible server-side).
- Total cost treats the API as ground truth; JSONL-derived output tokens are
  marked estimated.
"""

from __future__ import annotations


def tie_out(jsonl_daily: dict, api_daily: dict) -> dict:
    """Compare JSONL-derived daily dollars against API buckets per stream.

    Returns the reconciliation report with % divergence per day per stream
    and the divergence ledger.
    """
    raise NotImplementedError("Issue 8 — docs/issues/issue-08.md")
