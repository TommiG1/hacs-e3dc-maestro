"""Tariff slot scheduler used by the Maestro rule engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .control_engine import MaestroParams

TARIFF_HIGH = "high"
TARIFF_LOW = "low"
TARIFF_NORMAL = "normal"


@dataclass
class TariffSlot:
    """A recurring tariff window pinned to a set of weekdays."""

    weekdays: frozenset[int]   # 0=Mon … 6=Sun
    start_h: float             # fractional hour of day [0, 24)
    end_h: float               # fractional hour of day, may be < start_h to span midnight
    class_: str = TARIFF_HIGH  # "high" | "low" | "normal"
    min_reserve_soc: float | None = None  # optional explicit reserve floor for this slot


@dataclass
class TariffSchedule:
    """Collection of tariff slots plus an optional dynamic-price source."""

    slots: list[TariffSlot] = field(default_factory=list)
    dynamic_source_entity: str | None = None
    cheap_threshold: float | None = None  # €/kWh – price <= threshold ⇒ "low"


def _slot_active(slot: TariffSlot, weekday: int, hour: float) -> bool:
    """True if the slot covers (weekday, fractional hour-of-day)."""
    if slot.start_h <= slot.end_h:
        if weekday not in slot.weekdays:
            return False
        return slot.start_h <= hour < slot.end_h
    if weekday in slot.weekdays and hour >= slot.start_h:
        return True
    prev_day = (weekday - 1) % 7
    if prev_day in slot.weekdays and hour < slot.end_h:
        return True
    return False


def current_tariff_class(
    now: datetime,
    schedule: TariffSchedule,
    current_price: float | None = None,
) -> str:
    """Resolve the active tariff class for ``now``."""
    weekday = now.weekday()
    hour = now.hour + now.minute / 60.0

    matched: set[str] = set()
    for slot in schedule.slots:
        if _slot_active(slot, weekday, hour):
            matched.add(slot.class_)

    if TARIFF_HIGH in matched:
        return TARIFF_HIGH
    if (
        schedule.cheap_threshold is not None
        and current_price is not None
        and current_price <= schedule.cheap_threshold
    ):
        return TARIFF_LOW
    if TARIFF_LOW in matched:
        return TARIFF_LOW
    return TARIFF_NORMAL


def active_tariff_slot(now: datetime, schedule: TariffSchedule) -> TariffSlot | None:
    """Return the highest-priority active slot (high > low > normal) or None."""
    weekday = now.weekday()
    hour = now.hour + now.minute / 60.0
    priority = {TARIFF_HIGH: 0, TARIFF_LOW: 1, TARIFF_NORMAL: 2}
    best: TariffSlot | None = None
    for slot in schedule.slots:
        if not _slot_active(slot, weekday, hour):
            continue
        if best is None or priority.get(slot.class_, 99) < priority.get(best.class_, 99):
            best = slot
    return best


def tariff_schedule_from_params(params: MaestroParams) -> TariffSchedule:
    """Derive a TariffSchedule from the legacy ``ht_*`` + cheap-threshold params."""
    if params.tariff_schedule is not None:
        return params.tariff_schedule

    slots: list[TariffSlot] = []
    if params.ht_enabled:
        weekdays: set[int] = {0, 1, 2, 3, 4}
        if params.ht_sat:
            weekdays.add(5)
        if params.ht_sun:
            weekdays.add(6)
        slots.append(
            TariffSlot(
                weekdays=frozenset(weekdays),
                start_h=float(params.ht_on),
                end_h=float(params.ht_off),
                class_=TARIFF_HIGH,
            )
        )
    threshold = (
        params.cheap_threshold
        if params.dynamic_tariff_enabled
        else None
    )
    return TariffSchedule(slots=slots, cheap_threshold=threshold)
