"""Forecast cache, optimizer scheduling, and PV profile reading."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    CONF_PV_FORECAST_ENABLED,
    CONF_PV_FORECAST_SENSOR,
    CONF_PV_FORECAST_SENSOR_DAY2,
    CONF_TOMORROW_PV_SENSOR,
)
from .coordinator_helpers import (
    forecast_input_fingerprint as _forecast_input_fingerprint,
    quarter_slot as _quarter_slot,
    _run_optimizer_sync,
)
from .forecast import simulate_next_24h

_LOGGER = logging.getLogger(__name__)


class CoordinatorForecastMixin:
    async def _async_update_forecast(
        self, state: "MaestroState", now: datetime
    ) -> None:
        """F1: Recompute the 24-hour forecast using current stats (cached)."""
        try:
            cons_h = (
                self._consumption_stats.hourly_profile_w
                if self._consumption_stats is not None
                and any(v > 0 for v in self._consumption_stats.hourly_profile_w)
                else None
            )
            pv_h = (
                self._pv_stats.hourly_profile_w
                if self._pv_stats is not None
                and any(v > 0 for v in self._pv_stats.hourly_profile_w)
                else None
            )
            if cons_h is None and pv_h is None:
                return  # No historical data yet

            cons_used = cons_h if cons_h is not None else [state.house_power] * 24
            pv_used = pv_h if pv_h is not None else [state.pv_power] * 24
            params_key = (
                self._params.morning_cap_enabled,
                self._params.morning_cap_soc,
                self._params.morning_cap_until_h,
                self._params.charge_target,
                self._params.max_charge_power,
                self._params.feed_in_limit_percent,
                self._params.installed_kwp,
                self._params.battery_capacity_kwh,
            )
            fingerprint = _forecast_input_fingerprint(
                soc=state.soc,
                regelung_aktiv=self.regelung_aktiv,
                cons_h=cons_used,
                pv_h=pv_used,
                params_key=params_key,
                quarter=_quarter_slot(now),
            )
            if (
                self.forecast is not None
                and self._forecast_fingerprint == fingerprint
            ):
                return
            self.forecast = simulate_next_24h(
                soc=state.soc,
                consumption_h=cons_used,
                pv_h=pv_used,
                params=self._params,
                now=now,
                battery_capacity_kwh=self._params.battery_capacity_kwh,
                regelung_aktiv=self.regelung_aktiv,
            )
            self._forecast_fingerprint = fingerprint
        except Exception as err:
            _LOGGER.debug("Forecast update failed: %s", err)


    async def _async_maybe_run_optimizer(
        self, state: "MaestroState", now: datetime
    ) -> None:
        """F3: Run grid-search optimizer 1×/day when auto-mode is on.

        - Only runs when ``auto_mode_enabled`` is True
        - Only runs when no override exists for the current local date
        - Requires ≥7 days of consumption AND PV history; falls back otherwise
        - Manual entity writes invalidate the override and force a re-run
        """
        if not self._params.auto_mode_enabled:
            # Auto-mode off → make sure no stale override is applied
            if self._auto_params is not None:
                self.invalidate_auto_params()
            return

        # Only re-run when we haven't optimised for today (local date).
        # NOTE: do NOT gate on ``self._auto_params`` – that field is None when
        # baseline turned out optimal (no override needed).  Re-running every
        # update would only re-evaluate the same daily forecast.
        today = now.date()
        if self._auto_last_run is not None and self._auto_last_run.date() == today:
            return

        cs = self._consumption_stats
        pv = self._pv_stats
        if cs is None or pv is None:
            _LOGGER.warning(
                "Auto-Optimizer: cs=%s pv=%s – Sensor-Konfiguration unvollständig",
                cs, pv,
            )
            return  # missing sensor configuration

        cons_h = list(cs.hourly_profile_w)
        pv_h = list(pv.hourly_profile_w)
        if not any(v > 0 for v in cons_h) or not any(v > 0 for v in pv_h):
            _LOGGER.warning(
                "Auto-Optimizer: Profil leer – cons_max=%.0f pv_max=%.0f "
                "(cons_days=%s, pv_days=%s) – warte auf Statistik",
                max(cons_h) if cons_h else 0, max(pv_h) if pv_h else 0,
                cs.data_days, pv.data_days,
            )
            return  # no useful profile yet

        # If a Solcast/Forecast.Solar sensor provides today's hourly PV
        # profile (as a list/dict attribute), prefer it over the historic mean.
        # Supported attribute shapes:
        #   list[float]  len=24 → direct hourly W values
        #   list[dict]   with 'pv_estimate'/'value' + 'period_start' keys (Solcast)
        # days_ahead: 0 = today, 1 = tomorrow
        pv_h_forecast = self._read_pv_forecast_profile(now, days_ahead=0)
        if pv_h_forecast is not None:
            pv_h = pv_h_forecast
            # Sum is in W per slot — convert to kWh based on resolution
            _slots_per_hour = max(1, len(pv_h_forecast) // 24)
            _kwh_total = sum(pv_h_forecast) / 1000.0 / _slots_per_hour
            _LOGGER.info(
                "Auto-Optimizer: Tagesprognose genutzt (max=%.0f W, sum=%.1f kWh, Auflösung=%d min)",
                max(pv_h_forecast), _kwh_total, 60 // _slots_per_hour,
            )
        else:
            _LOGGER.info(
                "Auto-Optimizer: keine Tagesprognose gefunden \u2192 90d-Mittel (max=%.0f W)",
                max(pv_h),
            )

        # Day-2 forecast (tomorrow relative to ``now``): when available,
        # the optimizer extends its horizon to 48 h so a low end-of-day-1 SoC
        # combined with a poor PV day 2 is correctly penalised.
        pv_h_day2 = self._read_pv_forecast_profile(now, days_ahead=1)
        if pv_h_day2 is not None:
            _slots_per_hour_d2 = max(1, len(pv_h_day2) // 24)
            _LOGGER.info(
                "Auto-Optimizer: Tag-2-Prognose genutzt (sum=%.1f kWh) \u2192 48 h-Horizont",
                sum(pv_h_day2) / 1000.0 / _slots_per_hour_d2,
            )

        try:
            result = await self.hass.async_add_executor_job(
                _run_optimizer_sync,
                self._params,
                state.soc,
                cons_h,
                pv_h,
                self._params.battery_capacity_kwh,
                self.regelung_aktiv,
                self._params.inverter_power,
                self._params.auto_mode_objective,
                now,
                cs.data_days,
                pv.data_days,
                pv_h_day2,
            )
        except Exception as err:
            _LOGGER.warning("Optimizer run failed: %s", err)
            self._auto_params = None
            self._auto_result = None
            self._auto_last_run = now
            return

        self._auto_result = result
        self._auto_last_run = now
        if result.fallback or not result.overrides:
            # No improvement found / fallback → keep manual params active
            self._auto_params = None
            if result.fallback:
                _LOGGER.warning(
                    "Auto-Optimizer Fallback: %s (cons_days=%s, pv_days=%s)",
                    result.fallback_reason, cs.data_days, pv.data_days,
                )
            else:
                fc = result.forecast
                _LOGGER.info(
                    "Auto-Optimizer: Baseline optimal (Ziel=%s, Score=%.3f, Grid=%d, "
                    "Curtail=%.2f kWh, Feed=%.2f kWh, Draw=%.2f kWh, Autarkie=%.2f)",
                    result.objective, result.best_score, result.grid_size,
                    fc.pv_curtailed_kwh if fc else 0.0,
                    fc.grid_feed_in_kwh if fc else 0.0,
                    fc.grid_draw_kwh if fc else 0.0,
                    fc.self_sufficiency if fc and fc.self_sufficiency is not None else 0.0,
                )
        else:
            self._auto_params = result.best_params
            _LOGGER.info(
                "Auto-Optimizer aktiv (Ziel=%s): %s → +%.1f%%",
                result.objective, result.overrides, result.estimated_savings_pct,
            )


    def _read_pv_forecast_profile(
        self, now: "datetime", days_ahead: int = 0
    ) -> list[float] | None:
        """Try to read a 24h PV forecast (W) from a Solcast/Forecast.Solar sensor.

        Returns a list[float] with **either 24 hourly or 48 half-hourly** mean W
        values (UTC). The simulator (forecast.py) auto-detects the resolution
        from the array length; preserving the higher resolution lets the
        optimiser see PV peaks above the feed-in limit that would otherwise be
        averaged out by hourly bucketing (relevant for plants with strict
        feed-in caps like the 70 % rule).

        ``days_ahead`` selects which forecast day to extract:
        ``0`` = today (local date of ``now``), ``1`` = tomorrow.
        """
        import datetime as _dt

        def _parse_iso(s: str) -> "_dt.datetime | None":
            try:
                return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None

        target_date = (now + _dt.timedelta(days=days_ahead)).date()
        # Profiles are indexed by UTC hour-of-day (matching consumption/pv stats).
        _UTC = _dt.timezone.utc

        def _to_utc_slot(ts: _dt.datetime) -> tuple[_dt.date, int, int]:
            """Return (date, hour, minute) in UTC."""
            if ts.tzinfo is not None:
                ts_utc = ts.astimezone(_UTC)
            else:
                ts_utc = ts.replace(tzinfo=_UTC)
            return ts_utc.date(), ts_utc.hour, ts_utc.minute

        def _try_extract(attrs) -> list[float] | None:
            # Shape 1: list of dicts with period_start + pv_estimate (kW)
            for key in ("detailedHourly", "forecast", "hourly_data", "forecasts"):
                raw = attrs.get(key)
                if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                    # Collect into 48 half-hour buckets to preserve sub-hour peaks.
                    halfhour: list[list[float]] = [[] for _ in range(48)]
                    for item in raw:
                        ts_str = (
                            item.get("period_start")
                            or item.get("time")
                            or item.get("datetime")
                        )
                        if not ts_str:
                            continue
                        ts = _parse_iso(str(ts_str))
                        if ts is None:
                            continue
                        utc_date, utc_hour, utc_minute = _to_utc_slot(ts)
                        if utc_date != target_date:
                            continue
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
                    # Did we get genuine sub-hour data? (any hour has both halves filled)
                    has_halfhour = any(
                        halfhour[h * 2] and halfhour[h * 2 + 1]
                        for h in range(24)
                    )
                    if has_halfhour:
                        # Fill empty slots from the matching hour mean (rare gaps).
                        profile_48 = []
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
                    # Fallback to hourly resolution if data is hour-only.
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
                    ts = _parse_iso(str(k))
                    if ts is None:
                        continue
                    utc_date, utc_hour, _ = _to_utc_slot(ts)
                    if utc_date != target_date:
                        continue
                    try:
                        buckets[utc_hour].append(float(v))
                    except (TypeError, ValueError):
                        pass
                profile = [sum(b) / len(b) if b else 0.0 for b in buckets]
                if any(v > 0 for v in profile):
                    return profile
            return None

        opts = self.entry.options
        if not opts.get(CONF_PV_FORECAST_ENABLED):
            return None

        # 1. Try configured sensors (first match with data for target_date wins).
        # Tag-2 of the 48 h horizon is calendar tomorrow (days_ahead=1), not
        # Solcast "Tag 3"/übermorgen. Prefer the Forward-Looking tomorrow
        # sensor (same day), then an explicit day-2 override, then the main
        # forecast sensor.
        if days_ahead >= 1:
            candidate_ids = [
                opts.get(CONF_TOMORROW_PV_SENSOR),
                opts.get(CONF_PV_FORECAST_SENSOR_DAY2),
                opts.get(CONF_PV_FORECAST_SENSOR),
            ]
        else:
            candidate_ids = [opts.get(CONF_PV_FORECAST_SENSOR)]

        seen: set[str] = set()
        for sensor_id in candidate_ids:
            if not sensor_id or sensor_id in seen:
                continue
            seen.add(sensor_id)
            state = self.hass.states.get(sensor_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            profile = _try_extract(state.attributes)
            if profile is not None:
                if days_ahead >= 1:
                    _LOGGER.debug(
                        "PV-Profil Tag+%s aus '%s' (target=%s)",
                        days_ahead, sensor_id, target_date,
                    )
                return profile

        # 2. Auto-detect: scan all sensor.* states for one with detailedHourly/forecast/watt_hours
        # Only for days_ahead=0 — for tomorrow we require configured sensors so
        # Solcast Tag-3..7 entities cannot silently extend the horizon to 48 h.
        if days_ahead != 0:
            return None

        # Use cached result from a previous scan to avoid rescanning every cycle.
        if self._autodetected_pv_sensor is not None:
            cached_state = self.hass.states.get(self._autodetected_pv_sensor)
            if cached_state is not None and cached_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                profile = _try_extract(cached_state.attributes)
                if profile is not None:
                    return profile
            # Cached sensor is gone or no longer usable – clear cache and re-scan below.
            _LOGGER.info(
                "Auto-Optimizer: Gecachter PV-Sensor '%s' nicht mehr verfügbar – erneute Suche",
                self._autodetected_pv_sensor,
            )
            self._autodetected_pv_sensor = None

        for state in self.hass.states.async_all("sensor"):
            attrs = state.attributes
            if not any(
                k in attrs
                for k in ("detailedHourly", "forecast", "hourly_data", "watt_hours")
            ):
                continue
            profile = _try_extract(attrs)
            if profile is not None:
                self._autodetected_pv_sensor = state.entity_id
                _LOGGER.info(
                    "Auto-Optimizer: PV-Tagesprognose aus '%s' erkannt – wird für weitere Zyklen gecacht. "
                    "Tipp: Sensor in der Integration konfigurieren, um Auto-Erkennung zu deaktivieren.",
                    state.entity_id,
                )
                return profile

        return None
