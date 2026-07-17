"""Phase D: Rolling consumption statistics from HA Recorder.

Loads hourly statistics for the configured house-power sensor and exposes:
- ``avg_w_24h``: rolling 24h mean (W)
- ``avg_w_ht_window``: rolling mean restricted to hours covered by the active
  HT tariff slot (W)
- ``data_days``: how many distinct calendar days are represented in the data

Refreshed at most once per hour to keep recorder load low.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .control_engine import TariffSlot

_LOGGER = logging.getLogger(__name__)
_REFRESH_INTERVAL = timedelta(hours=1)


def _hour_in_slot(hour_local: float, weekday: int, slot: TariffSlot) -> bool:
    """True if ``(weekday, hour)`` is covered by ``slot``."""
    if slot.start_h <= slot.end_h:
        if weekday not in slot.weekdays:
            return False
        return slot.start_h <= hour_local < slot.end_h
    if weekday in slot.weekdays and hour_local >= slot.start_h:
        return True
    prev_day = (weekday - 1) % 7
    if prev_day in slot.weekdays and hour_local < slot.end_h:
        return True
    return False


class ConsumptionStats:
    """Async helper that pulls hourly mean values for a power sensor."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self.avg_w_24h: float | None = None
        self.avg_w_ht_window: float | None = None
        self.data_days: int = 0
        self.hourly_profile_w: list[float] = [0.0] * 24  # avg W per hour-of-day
        # F1+: 7×24 Profil pro (Wochentag 0=Mo, Stunde 0–23) in W
        self.weekday_profile_w: list[list[float]] = [
            [0.0] * 24 for _ in range(7)
        ]
        self._last_refresh: datetime | None = None

    async def async_refresh(
        self,
        lookback_days: int,
        ht_slot: TariffSlot | None,
        *,
        force: bool = False,
        backfill_days: int = 90,
    ) -> None:
        """Refresh statistics from the recorder (once per hour unless forced).

        On the very first call (no prior refresh), ``backfill_days`` is used as
        the lookback window so that existing sensor history is loaded immediately
        rather than waiting for ``lookback_days`` worth of new data.
        """
        now = dt_util.utcnow()
        if (
            not force
            and self._last_refresh is not None
            and now - self._last_refresh < _REFRESH_INTERVAL
        ):
            return

        # First-run backfill: use the longer window to populate hourly profile
        # from existing recorder history immediately after installation.
        effective_days = (
            max(lookback_days, backfill_days)
            if self._last_refresh is None
            else lookback_days
        )

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
        except Exception as err:  # pragma: no cover – HA always provides recorder
            _LOGGER.debug("Recorder not available, skipping stats: %s", err)
            self._last_refresh = now
            return

        start = now - timedelta(days=max(1, effective_days))
        try:
            stats: dict[str, list[dict[str, Any]]] = await get_instance(
                self._hass
            ).async_add_executor_job(
                statistics_during_period,
                self._hass,
                start,
                now,
                {self._entity_id},
                "hour",
                None,
                {"mean"},
            )
        except Exception as err:
            _LOGGER.warning(
                "Konnte Statistiken für %s nicht laden: %s", self._entity_id, err
            )
            self._last_refresh = now
            return

        rows = (stats or {}).get(self._entity_id) or []
        if not rows:
            self.avg_w_24h = None
            self.avg_w_ht_window = None
            self.data_days = 0
            self._last_refresh = now
            return

        # Detect sensor unit (W vs. kW) from the entity state and normalize to W
        scale = 1.0
        state_obj = self._hass.states.get(self._entity_id)
        if state_obj is not None:
            unit = (state_obj.attributes.get("unit_of_measurement") or "").strip()
            if unit.lower() in ("kw", "kilowatt"):
                scale = 1000.0
        if scale != 1.0:
            for row in rows:
                if row.get("mean") is not None:
                    row["mean"] = float(row["mean"]) * scale

        self._update_from_rows(rows, ht_slot)
        self._last_refresh = now

    # ------------------------------------------------------------------
    # Pure update logic, isolated for unit testing.
    # ------------------------------------------------------------------
    def _update_from_rows(
        self, rows: list[dict[str, Any]], ht_slot: TariffSlot | None
    ) -> None:
        days: set[Any] = set()
        all_means: list[float] = []
        ht_means: list[float] = []
        for row in rows:
            mean = row.get("mean")
            if mean is None:
                continue
            start_ts = row.get("start")
            local = _row_to_local(start_ts)
            if local is None:
                continue
            days.add(local.date())
            value = abs(float(mean))
            all_means.append(value)
            if ht_slot is not None:
                hour_local = local.hour + local.minute / 60.0
                if _hour_in_slot(hour_local, local.weekday(), ht_slot):
                    ht_means.append(value)

        self.data_days = len(days)
        self.avg_w_24h = sum(all_means) / len(all_means) if all_means else None
        if ht_slot is not None and ht_means:
            self.avg_w_ht_window = sum(ht_means) / len(ht_means)
        else:
            self.avg_w_ht_window = None

        # Build 24-slot hourly profile (grouped by UTC hour-of-day so it matches
        # forecast.py / optimizer lookups which index profiles in UTC).
        buckets: list[list[float]] = [[] for _ in range(24)]
        weekday_buckets: list[list[list[float]]] = [
            [[] for _ in range(24)] for _ in range(7)
        ]
        for row in rows:
            mean = row.get("mean")
            if mean is None:
                continue
            utc = _row_to_utc(row.get("start"))
            if utc is None:
                continue
            value = abs(float(mean))
            buckets[utc.hour].append(value)
            weekday_buckets[utc.weekday()][utc.hour].append(value)
        self.hourly_profile_w = [
            sum(b) / len(b) if b else 0.0 for b in buckets
        ]
        self.weekday_profile_w = [
            [sum(b) / len(b) if b else 0.0 for b in day]
            for day in weekday_buckets
        ]

    # ------------------------------------------------------------------
    # F1+: Wochentag-spezifischer Tagesverbrauch
    # ------------------------------------------------------------------
    def weekday_total_kwh(self, weekday: int) -> float | None:
        """Erwarteter Tages-Verbrauch (kWh) für ``weekday`` (0=Mo, 6=So).

        Fallback auf 24h-Mittel wenn das Wochentags-Profil leer ist (z.B. bei
        zu wenig Historie). Rückgabe ``None`` wenn auch kein 24h-Mittel da ist.
        """
        if not (0 <= weekday < 7):
            return None
        day_profile = self.weekday_profile_w[weekday]
        total_w_h = sum(day_profile)
        if total_w_h > 0:
            return total_w_h / 1000.0  # 24 Stunden × W → kWh
        # Fallback: 24h-Mittelwert
        if self.avg_w_24h is not None and self.avg_w_24h > 0:
            return self.avg_w_24h * 24.0 / 1000.0
        return None

    def peak_daily_yield_kwh(self) -> float | None:
        """Historischer Tages-Peak (kWh) als Proxy für einen sonnigen Referenztag.

        Liefert das Maximum der Wochentags-Tagessummen (Σ Stundenmittel pro
        Wochentag, dividiert durch 1000). Rückgabe ``None`` wenn das Profil
        leer ist (z. B. zu wenig Historie). Wird vom Coordinator nur genutzt
        wenn ``data_days >= 7``.

        Auf reinen PV-Sensoren entspricht der Rückgabewert dem durchschnittlich
        besten Tagesertrag des bislang besten Wochentags – das unterschätzt
        Spitzentage, ist aber ein konservatives, robustes Maß.
        """
        totals: list[float] = []
        for day in self.weekday_profile_w:
            day_total = sum(day)
            if day_total > 0:
                totals.append(day_total)
        if not totals:
            return None
        return max(totals) / 1000.0


def _row_to_local(start_ts: Any) -> datetime | None:
    """Convert a recorder statistics row's ``start`` field to a local datetime."""
    utc = _row_to_utc(start_ts)
    if utc is None:
        return None
    return dt_util.as_local(utc)


def _row_to_utc(start_ts: Any) -> datetime | None:
    """Convert a recorder statistics row's ``start`` field to UTC datetime."""
    if start_ts is None:
        return None
    if isinstance(start_ts, (int, float)):
        return datetime.fromtimestamp(start_ts, tz=dt_util.UTC)
    if isinstance(start_ts, datetime):
        if start_ts.tzinfo is None:
            return start_ts.replace(tzinfo=dt_util.UTC)
        return start_ts.astimezone(dt_util.UTC)
    if isinstance(start_ts, str):
        try:
            parsed = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt_util.UTC)
        return parsed.astimezone(dt_util.UTC)
    return None
