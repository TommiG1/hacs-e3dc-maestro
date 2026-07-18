"""Pure PV forecast profile extraction (Solcast / Forecast.Solar).

Kept free of Home Assistant imports so unit tests can cover timezone and
attribute-shape edge cases without stubs.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

FORECAST_LIST_KEYS = (
    "detailedForecast",
    "detailedHourly",
    "forecast",
    "hourly_data",
    "forecasts",
)
FORECAST_ATTR_KEYS = FORECAST_LIST_KEYS + ("watt_hours", "hourly_wh", "watt_hours_period", "watt")


def parse_iso(s: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def period_calendar_date(ts: _dt.datetime) -> _dt.date:
    """Wall-clock calendar date as labeled in the forecast period.

    Keep the date from the ISO string / sensor (local day), not the UTC date —
    otherwise CEST midnight→01:59 falls on "yesterday".
    """
    return ts.date()


def to_utc_slot(ts: _dt.datetime) -> tuple[int, int]:
    """Return (hour, minute) in UTC."""
    _UTC = _dt.timezone.utc
    if ts.tzinfo is not None:
        ts_utc = ts.astimezone(_UTC)
    else:
        ts_utc = ts.replace(tzinfo=_UTC)
    return ts_utc.hour, ts_utc.minute


def unique_calendar_dates_in_attrs(attrs: dict[str, Any]) -> set[_dt.date]:
    """Collect distinct calendar dates present in forecast list/dict attributes."""
    dates: set[_dt.date] = set()
    for key in FORECAST_LIST_KEYS:
        raw = attrs.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts_str = item.get("period_start") or item.get("time") or item.get("datetime")
            if not ts_str:
                continue
            ts = parse_iso(str(ts_str))
            if ts is not None:
                dates.add(period_calendar_date(ts))
    raw_wh = attrs.get("watt_hours")
    if isinstance(raw_wh, dict):
        for k in raw_wh:
            ts = parse_iso(str(k))
            if ts is not None:
                dates.add(period_calendar_date(ts))
    return dates


def is_single_day_forecast(attrs: dict[str, Any]) -> bool:
    """True when attributes contain forecast periods for at most one calendar day."""
    dates = unique_calendar_dates_in_attrs(attrs)
    return len(dates) <= 1


def extract_pv_profile(
    attrs: dict[str, Any],
    *,
    target_date: _dt.date,
    ignore_date: bool = False,
) -> list[float] | None:
    """Extract a 24h (or 48 half-hour) PV profile in W from sensor attributes.

    Returns ``None`` when no usable positive profile for *target_date* is found
    (unless ``ignore_date`` is set, in which case all periods are accepted).
    """
    # Shape 1: list of dicts with period_start + pv_estimate (kW)
    for key in FORECAST_LIST_KEYS:
        raw = attrs.get(key)
        if not (isinstance(raw, list) and raw and isinstance(raw[0], dict)):
            continue
        halfhour: list[list[float]] = [[] for _ in range(48)]
        for item in raw:
            ts_str = (
                item.get("period_start")
                or item.get("time")
                or item.get("datetime")
            )
            if not ts_str:
                continue
            ts = parse_iso(str(ts_str))
            if ts is None:
                continue
            if not ignore_date and period_calendar_date(ts) != target_date:
                continue
            utc_hour, utc_minute = to_utc_slot(ts)
            val = (
                item.get("pv_estimate")
                or item.get("value")
                or item.get("pv_estimate90")
                or 0.0
            )
            try:
                val_w = float(val) * 1000.0  # kW → W
            except (TypeError, ValueError):
                continue
            slot = utc_hour * 2 + (1 if utc_minute >= 30 else 0)
            halfhour[slot].append(val_w)
        has_halfhour = any(
            halfhour[h * 2] and halfhour[h * 2 + 1] for h in range(24)
        )
        if has_halfhour:
            profile_48: list[float] = []
            for h in range(24):
                a = halfhour[h * 2]
                b = halfhour[h * 2 + 1]
                if a and b:
                    profile_48.append(sum(a) / len(a))
                    profile_48.append(sum(b) / len(b))
                elif a or b:
                    vals = a or b
                    avg = sum(vals) / len(vals)
                    profile_48.append(avg)
                    profile_48.append(avg)
                else:
                    profile_48.append(0.0)
                    profile_48.append(0.0)
            if any(v > 0 for v in profile_48):
                return profile_48
        profile_24 = []
        for h in range(24):
            vals = halfhour[h * 2] + halfhour[h * 2 + 1]
            profile_24.append(sum(vals) / len(vals) if vals else 0.0)
        if any(v > 0 for v in profile_24):
            return profile_24

    # Shape 2: plain list len=24
    for key in ("hourly_wh", "watt_hours_period", "watt"):
        raw = attrs.get(key)
        if isinstance(raw, list) and len(raw) == 24:
            try:
                return [float(v) for v in raw]
            except (TypeError, ValueError):
                pass

    # Shape 3: dict with ISO datetime keys → Wh (hourly buckets)
    raw = attrs.get("watt_hours")
    if isinstance(raw, dict):
        buckets: list[list[float]] = [[] for _ in range(24)]
        for k, v in raw.items():
            ts = parse_iso(str(k))
            if ts is None:
                continue
            if not ignore_date and period_calendar_date(ts) != target_date:
                continue
            utc_hour, _ = to_utc_slot(ts)
            try:
                buckets[utc_hour].append(float(v))
            except (TypeError, ValueError):
                pass
        profile = [sum(b) / len(b) if b else 0.0 for b in buckets]
        if any(v > 0 for v in profile):
            return profile
    return None


def forecast_params_key(params: Any) -> tuple[Any, ...]:
    """Stable fingerprint of simulation-relevant MaestroParams fields."""
    return (
        getattr(params, "morning_cap_enabled", False),
        getattr(params, "morning_cap_soc", None),
        getattr(params, "morning_cap_until_h", None),
        getattr(params, "charge_target", None),
        getattr(params, "charge_threshold", None),
        getattr(params, "max_charge_power", None),
        getattr(params, "min_charge_power", None),
        getattr(params, "feed_in_limit_percent", None),
        getattr(params, "installed_kwp", None),
        getattr(params, "battery_capacity_kwh", None),
        getattr(params, "inverter_power", None),
        getattr(params, "spreading_enabled", None),
        getattr(params, "spreading_target_soc", None),
        getattr(params, "pv_forecast_enabled", None),
        getattr(params, "pv_forecast_threshold_kwh", None),
        getattr(params, "pv_forecast_safety_factor", None),
        getattr(params, "gentle_charge_enabled", None),
        getattr(params, "gentle_charge_factor", None),
        getattr(params, "low_yield_priority_enabled", None),
        getattr(params, "low_yield_threshold", None),
        getattr(params, "forward_looking_enabled", None),
        getattr(params, "forward_looking_max_soc", None),
        getattr(params, "hard_soc_limit_enabled", None),
        getattr(params, "hard_soc_limit", None),
        getattr(params, "ht_enabled", None),
        getattr(params, "ht_min", None),
        getattr(params, "ht_on", None),
        getattr(params, "ht_off", None),
        getattr(params, "adaptive_reserve_enabled", None),
        getattr(params, "seasonal_reserve_enabled", None),
        getattr(params, "astro_enabled", None),
        getattr(params, "curtailment_guard_enabled", None),
        getattr(params, "auto_mode_enabled", None),
        getattr(params, "auto_mode_objective", None),
    )


def profile_source_tag(source: str | None, profile: list[float] | None) -> tuple[Any, ...]:
    """Include PV source identity in the forecast fingerprint."""
    if profile is None:
        return (source, None, 0)
    return (source, len(profile), round(sum(profile), 1))
