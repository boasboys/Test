"""Pricing engine — LOAD-BEARING (CLAUDE.md invariant 1).

Implemented by Issue 3 (docs/issues/issue-03.md). Once merged, agents must not
edit this file directly; propose changes in the PR description instead.

Contract:
- Costs come from a dated snapshot in pricing/*.yaml; every dollar figure
  carries the snapshot ID it was computed with (invariant 4).
- An unknown model raises UnknownModelError — never a silent $0.
- All arithmetic is Decimal; rates are USD per million tokens. Cache-write
  and cache-read multipliers apply to the base input rate; the batch
  multiplier applies to every stream.
- output_tokens are streaming placeholders, so output cost is flagged
  estimated throughout.
- Not yet modeled (propose via PR when the corpus needs them):
  inference_geo and long-context premiums.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from tokenlens.ingest.parser import Event

_MTOK = Decimal(1_000_000)


class UnknownModelError(Exception):
    """Raised when an event's model has no entry in the pricing snapshot."""


class SnapshotError(Exception):
    """Raised when a pricing snapshot is missing, malformed, or incomplete."""


@dataclass(frozen=True, slots=True)
class ModelRates:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    verified: bool
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    batch: Decimal
    models: dict[str, ModelRates]


@dataclass(frozen=True, slots=True)
class EventCost:
    """Cost of one corrected event. Always carries its snapshot_id."""

    snapshot_id: str
    model: str
    input_usd: Decimal
    cache_write_usd: Decimal
    cache_read_usd: Decimal
    output_usd_estimated: Decimal

    @property
    def total_usd(self) -> Decimal:
        return (
            self.input_usd
            + self.cache_write_usd
            + self.cache_read_usd
            + self.output_usd_estimated
        )


def _decimal(raw: object, field: str) -> Decimal:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise SnapshotError(f"snapshot field {field} must be numeric, got {raw!r}")
    return Decimal(str(raw))


def load_snapshot(path: Path) -> Snapshot:
    """Load and validate one dated pricing snapshot (yaml.safe_load only)."""
    if not path.is_file():
        raise SnapshotError(f"pricing snapshot not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SnapshotError(f"snapshot is not a mapping: {path}")
    try:
        multipliers = data["multipliers"]
        models_raw = data["models"]
        snapshot_id = str(data["snapshot_id"])
    except KeyError as exc:
        raise SnapshotError(f"snapshot {path} missing required key: {exc}") from exc

    models: dict[str, ModelRates] = {}
    for model, rates in models_raw.items():
        models[str(model)] = ModelRates(
            input_per_mtok=_decimal(rates.get("input_per_mtok"), f"{model}.input_per_mtok"),
            output_per_mtok=_decimal(rates.get("output_per_mtok"), f"{model}.output_per_mtok"),
        )
    if not models:
        raise SnapshotError(f"snapshot {path} defines no models")

    return Snapshot(
        snapshot_id=snapshot_id,
        verified=bool(data.get("verified", False)),
        cache_write_5m=_decimal(multipliers.get("cache_write_5m"), "cache_write_5m"),
        cache_write_1h=_decimal(multipliers.get("cache_write_1h"), "cache_write_1h"),
        cache_read=_decimal(multipliers.get("cache_read"), "cache_read"),
        batch=_decimal(multipliers.get("batch"), "batch"),
        models=models,
    )


def latest_snapshot(pricing_dir: Path) -> Snapshot:
    """Load the most recent dated snapshot in a pricing directory."""
    candidates = sorted(pricing_dir.glob("*.yaml"))
    if not candidates:
        raise SnapshotError(f"no pricing snapshots (*.yaml) in {pricing_dir}")
    return load_snapshot(candidates[-1])


def cost_event(event: Event, snapshot: Snapshot) -> EventCost:
    """Price one corrected event against a snapshot.

    Raises UnknownModelError for models absent from the snapshot — a cost of
    $0 for an unknown model is never acceptable (invariant 4).
    """
    rates = snapshot.models.get(event.model)
    if rates is None:
        raise UnknownModelError(
            f"model {event.model!r} not in pricing snapshot {snapshot.snapshot_id!r} "
            f"(event {event.message_id} in {event.source_file}) — refusing to price as $0"
        )
    in_rate = rates.input_per_mtok
    batch = snapshot.batch if event.service_tier == "batch" else Decimal(1)

    input_usd = Decimal(event.input_tokens) * in_rate / _MTOK
    cache_write_usd = (
        Decimal(event.cache_creation_5m) * in_rate * snapshot.cache_write_5m
        + Decimal(event.cache_creation_1h) * in_rate * snapshot.cache_write_1h
    ) / _MTOK
    cache_read_usd = Decimal(event.cache_read_tokens) * in_rate * snapshot.cache_read / _MTOK
    output_usd = Decimal(event.output_tokens) * rates.output_per_mtok / _MTOK

    return EventCost(
        snapshot_id=snapshot.snapshot_id,
        model=event.model,
        input_usd=input_usd * batch,
        cache_write_usd=cache_write_usd * batch,
        cache_read_usd=cache_read_usd * batch,
        output_usd_estimated=output_usd * batch,
    )
