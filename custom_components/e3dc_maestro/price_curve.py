"""Pure price-curve extraction for dynamic tariffs (Nordpool, Tibber, aWATTar, ...).

Free of Home Assistant imports so unit tests can cover the attribute shapes.

Supported sensor attribute shapes (first match wins):

* ``raw_today`` / ``raw_tomorrow``  – list of ``{start, end?, value}`` (Nordpool HACS,
  Tibber-style template sensors, the aWATTar simulation sensor)
* ``today`` / ``tomorrow``          – list of floats, 24 (hourly), 48 (30 min) or
  96 (15 min) values starting at local midnight; ``None`` entries are unknown
* ``prices`` / ``data`` / ``forecast`` – flat list of dicts with ``startsAt`` / ``start`` /
  ``start_time`` / ``from`` / ``datetime`` and ``total`` / ``value`` / ``price`` /
  ``marketprice``

Prices are returned as-is (€/kWh expected). Unit conversion is the caller's job.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Any

_START_KEYS = ("start", "startsAt", "start_time", "from", "datetime", "period_start")
_END_KEYS = ("end", "endsAt", "end_time", "to")
_VALUE_KEYS = ("value", "total", "price", "marketprice")
_FLAT_LIST_KEYS = ("raw_today", "raw_tomorrow", "prices", "data", "forecast")
_FLOAT_LIST_RESOLUTIONS = {23: 1.0, 24: 1.0, 25: 1.0, 48: 0.5, 92: 0.25, 96: 0.25, 100: 0.25}
_GAP_TOLERANCE_S = 90.0
_TZ_NO_COLON = re.compile(r"([+-]\d{2})(\d{2})$")


@dataclass(frozen=True)
class PriceSlot:
    start: _dt.datetime  # timezone-aware
    end: _dt.datetime
    price: float

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass(frozen=True)
class PriceHorizon:
    """Contiguous known prices starting at ``start`` (= now)."""

    start: _dt.datetime
    slot_hours: list[float]
    prices: list[float]
    known_until: _dt.datetime

    @property
    def total_hours(self) -> float:
        return sum(self.slot_hours)


def _parse_dt(value: Any, tz: _dt.tzinfo | None) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        ts = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return _dt.datetime.fromtimestamp(seconds, tz=_dt.timezone.utc)
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        # "+0200" (strftime %z, e.g. template sensors) → "+02:00" for older parsers.
        text = _TZ_NO_COLON.sub(r"\1:\2", text)
        try:
            ts = _dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=tz or _dt.timezone.utc)
    return ts


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN guard


def _slots_from_dicts(raw: list[Any], tz: _dt.tzinfo | None) -> list[PriceSlot]:
    parsed: list[tuple[_dt.datetime, _dt.datetime | None, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = _parse_dt(_first(item, _START_KEYS), tz)
        price = _to_float(_first(item, _VALUE_KEYS))
        if start is None or price is None:
            continue
        end = _parse_dt(_first(item, _END_KEYS), tz)
        parsed.append((start, end, price))
    parsed.sort(key=lambda t: t[0])
    slots: list[PriceSlot] = []
    for i, (start, end, price) in enumerate(parsed):
        if end is None or end <= start:
            # No usable end: next start, else repeat the previous slot length, else 1 h.
            if i + 1 < len(parsed) and parsed[i + 1][0] > start:
                end = parsed[i + 1][0]
            elif slots:
                end = start + (slots[-1].end - slots[-1].start)
            else:
                end = start + _dt.timedelta(hours=1)
        slots.append(PriceSlot(start=start, end=end, price=price))
    return slots


def _slots_from_floats(values: list[Any], day: _dt.date, tz: _dt.tzinfo) -> list[PriceSlot]:
    step_h = _FLOAT_LIST_RESOLUTIONS.get(len(values))
    if step_h is None:
        return []
    midnight = _dt.datetime(day.year, day.month, day.day, tzinfo=tz)
    step = _dt.timedelta(hours=step_h)
    slots: list[PriceSlot] = []
    for i, raw in enumerate(values):
        price = _to_float(raw)
        if price is None:
            continue
        start = midnight + i * step
        slots.append(PriceSlot(start=start, end=start + step, price=price))
    return slots


def extract_price_slots(attrs: dict[str, Any], now: _dt.datetime) -> list[PriceSlot]:
    """Return all price slots found in ``attrs`` (sorted, de-duplicated by start)."""
    tz = now.tzinfo or _dt.timezone.utc
    slots: dict[_dt.datetime, PriceSlot] = {}

    # 1) Dict lists (several keys may carry today + tomorrow separately).
    for key in _FLAT_LIST_KEYS:
        raw = attrs.get(key)
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            for slot in _slots_from_dicts(raw, tz):
                slots.setdefault(slot.start, slot)

    # 2) Plain float lists for today/tomorrow – only if no dict data was found.
    if not slots:
        today = now.astimezone(tz).date()
        for key, offset in (("today", 0), ("tomorrow", 1)):
            raw = attrs.get(key)
            if isinstance(raw, list) and raw and not isinstance(raw[0], dict):
                day = today + _dt.timedelta(days=offset)
                for slot in _slots_from_floats(raw, day, tz):
                    slots.setdefault(slot.start, slot)

    return [slots[k] for k in sorted(slots)]


def build_horizon(
    slots: list[PriceSlot], now: _dt.datetime, max_hours: float = 48.0
) -> PriceHorizon | None:
    """Contiguous known prices from ``now`` on (current slot truncated to start at now)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    ordered = sorted(slots, key=lambda s: s.start)
    idx = next((i for i, s in enumerate(ordered) if s.start <= now < s.end), None)
    if idx is None:
        return None

    limit = now + _dt.timedelta(hours=max_hours)
    slot_hours: list[float] = []
    prices: list[float] = []
    cursor = now
    for slot in ordered[idx:]:
        if abs((slot.start - cursor).total_seconds()) > _GAP_TOLERANCE_S and slot is not ordered[idx]:
            break  # gap in the data → stop at last contiguous slot
        end = min(slot.end, limit)
        hours = (end - cursor).total_seconds() / 3600.0
        if hours <= 0:
            break
        slot_hours.append(hours)
        prices.append(slot.price)
        cursor = end
        if cursor >= limit:
            break
    if not prices:
        return None
    return PriceHorizon(start=now, slot_hours=slot_hours, prices=prices, known_until=cursor)


def read_price_horizon(
    attrs: dict[str, Any], now: _dt.datetime, max_hours: float = 48.0
) -> PriceHorizon | None:
    """Convenience: attributes → contiguous horizon from now (or ``None``)."""
    return build_horizon(extract_price_slots(attrs, now), now, max_hours)
