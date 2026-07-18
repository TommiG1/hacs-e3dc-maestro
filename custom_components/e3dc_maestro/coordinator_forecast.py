"""Forecast cache, optimizer scheduling, and PV profile reading."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    CONF_PV_FORECAST_ENABLED,
    CONF_PV_FORECAST_SENSOR,
    CONF_PV_FORECAST_SENSOR_DAY2,
    CONF_TOMORROW_PV_SENSOR,
)
from .coordinator_helpers import (
    _run_optimizer_sync,
    forecast_input_fingerprint as _forecast_input_fingerprint,
    quarter_slot as _quarter_slot,
)
from .forecast import simulate_next_24h
from .pv_forecast_profile import (
    FORECAST_ATTR_KEYS,
    extract_pv_profile,
    forecast_params_key,
    is_single_day_forecast,
    profile_source_tag,
)

if TYPE_CHECKING:
    from .control_engine import MaestroState

_LOGGER = logging.getLogger(__name__)

# How long to wait before retrying a failed optimizer run (same calendar day).
_OPTIMIZER_RETRY_HOURS = 1


class CoordinatorForecastMixin:
    async def _async_update_forecast(
        self, state: MaestroState, now: datetime
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
            # Prefer today's Solcast/Forecast.Solar profile when available so the
            # dashboard forecast matches the optimizer PV basis.
            pv_source = "historic_mean"
            pv_forecast = self._read_pv_forecast_profile(now, days_ahead=0)
            if pv_forecast is not None:
                pv_used = pv_forecast
                pv_source = "day_forecast"
            elif pv_h is not None:
                pv_used = pv_h
            else:
                pv_used = [state.pv_power] * 24
                pv_source = "instant"

            active = self._active_params
            params_key = forecast_params_key(active) + profile_source_tag(
                pv_source, pv_used if pv_source == "day_forecast" else None
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

            # Serialise concurrent simulations (poll tick vs. listener refresh).
            if not hasattr(self, "_forecast_lock"):
                self._forecast_lock = asyncio.Lock()
            async with self._forecast_lock:
                if (
                    self.forecast is not None
                    and self._forecast_fingerprint == fingerprint
                ):
                    return
                generation = getattr(self, "_forecast_generation", 0) + 1
                self._forecast_generation = generation

                def _run_sim(
                    _soc=state.soc,
                    _cons=cons_used,
                    _pv=pv_used,
                    _params=active,
                    _now=now,
                    _cap=active.battery_capacity_kwh,
                    _active=self.regelung_aktiv,
                ):
                    return simulate_next_24h(
                        soc=_soc,
                        consumption_h=_cons,
                        pv_h=_pv,
                        params=_params,
                        now=_now,
                        battery_capacity_kwh=_cap,
                        regelung_aktiv=_active,
                    )

                result = await self.hass.async_add_executor_job(_run_sim)
                if getattr(self, "_forecast_generation", 0) != generation:
                    return  # superseded by a newer request
                self.forecast = result
                self._forecast_fingerprint = fingerprint
                self._forecast_pv_source = pv_source
        except Exception as err:
            _LOGGER.debug("Forecast update failed: %s", err)


    async def _async_maybe_run_optimizer(
        self, state: MaestroState, now: datetime
    ) -> None:
        """F3: Run grid-search optimizer 1×/day when auto-mode is on.

        - Only runs when ``auto_mode_enabled`` is True
        - Only runs when no override exists for the current local date
        - Requires ≥7 days of consumption AND PV history; falls back otherwise
        - Manual entity writes invalidate the override and force a re-run
        - Failed runs retry after ``_OPTIMIZER_RETRY_HOURS`` (same day)
        """
        if not self._params.auto_mode_enabled:
            # Auto-mode off → make sure no stale override is applied
            if self._auto_params is not None:
                self.invalidate_auto_params()
            return

        today = now.date()
        if self._auto_last_run is not None and self._auto_last_run.date() == today:
            # Successful run today — do not re-evaluate until tomorrow.
            if not getattr(self, "_auto_run_failed", False):
                return
            # Failed earlier today — allow controlled retry.
            elapsed_h = (now - self._auto_last_run).total_seconds() / 3600.0
            if elapsed_h < _OPTIMIZER_RETRY_HOURS:
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
        pv_h_forecast = self._read_pv_forecast_profile(now, days_ahead=0)
        if pv_h_forecast is not None:
            pv_h = pv_h_forecast
            _slots_per_hour = max(1, len(pv_h_forecast) // 24)
            _kwh_total = sum(pv_h_forecast) / 1000.0 / _slots_per_hour
            _LOGGER.info(
                "Auto-Optimizer: Tagesprognose genutzt (max=%.0f W, sum=%.1f kWh, Auflösung=%d min)",
                max(pv_h_forecast), _kwh_total, 60 // _slots_per_hour,
            )
        else:
            _LOGGER.debug(
                "Auto-Optimizer: keine Tagesprognose gefunden → 90d-Mittel (max=%.0f W)",
                max(pv_h),
            )

        # Day-2 forecast (tomorrow relative to ``now``): when available,
        # the optimizer extends its horizon to 48 h so a low end-of-day-1 SoC
        # combined with a poor PV day 2 is correctly penalised.
        pv_h_day2 = self._read_pv_forecast_profile(now, days_ahead=1)
        if pv_h_day2 is not None:
            _slots_per_hour_d2 = max(1, len(pv_h_day2) // 24)
            _LOGGER.info(
                "Auto-Optimizer: Tag-2-Prognose genutzt (sum=%.1f kWh) → 48 h-Horizont",
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
            self._auto_run_failed = True
            # Invalidate forecast so next tick recomputes with manual params.
            self._forecast_fingerprint = None
            return

        self._auto_result = result
        self._auto_last_run = now
        self._auto_run_failed = False
        # Auto override changed → force forecast refresh with active params.
        self._forecast_fingerprint = None
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
        self, now: datetime, days_ahead: int = 0
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

        target_date = (now + _dt.timedelta(days=days_ahead)).date()
        opts = self.entry.options
        if not opts.get(CONF_PV_FORECAST_ENABLED):
            return None

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
            attrs = dict(state.attributes)
            profile = extract_pv_profile(attrs, target_date=target_date)
            # Solcast day entities (prognose_morgen / tag_N) only contain one
            # calendar day — if the strict date filter missed (UTC vs local),
            # accept the sensor's full profile for Tag-2 candidates ONLY when
            # the attribute payload is clearly single-day. Multi-day sensors
            # (e.g. wrongly configured Tag-3) must not silently become "tomorrow".
            if profile is None and days_ahead >= 1 and is_single_day_forecast(attrs):
                profile = extract_pv_profile(
                    attrs, target_date=target_date, ignore_date=True
                )
            if profile is not None:
                if days_ahead >= 1:
                    _LOGGER.debug(
                        "Auto-Optimizer: Tag-%s-Profil aus '%s' (target=%s, sum≈%.1f kWh)",
                        days_ahead + 1,
                        sensor_id,
                        target_date,
                        sum(profile) / 1000.0 / max(1, len(profile) // 24),
                    )
                return profile

        if days_ahead >= 1:
            _LOGGER.debug(
                "Auto-Optimizer: kein Tag-2-PV-Profil (target=%s, tried=%s)",
                target_date,
                [s for s in candidate_ids if s],
            )

        # Auto-detect: only for days_ahead=0 — for tomorrow we require configured
        # sensors so Solcast Tag-3..7 entities cannot silently extend the horizon.
        if days_ahead != 0:
            return None

        if self._autodetected_pv_sensor is not None:
            cached_state = self.hass.states.get(self._autodetected_pv_sensor)
            if cached_state is not None and cached_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                profile = extract_pv_profile(
                    dict(cached_state.attributes), target_date=target_date
                )
                if profile is not None:
                    return profile
            _LOGGER.debug(
                "Auto-Optimizer: Gecachter PV-Sensor '%s' nicht mehr verfügbar – erneute Suche",
                self._autodetected_pv_sensor,
            )
            self._autodetected_pv_sensor = None

        for state in self.hass.states.async_all("sensor"):
            attrs = state.attributes
            if not any(k in attrs for k in FORECAST_ATTR_KEYS):
                continue
            profile = extract_pv_profile(dict(attrs), target_date=target_date)
            if profile is not None:
                self._autodetected_pv_sensor = state.entity_id
                _LOGGER.info(
                    "Auto-Optimizer: PV-Tagesprognose aus '%s' erkannt – wird für weitere Zyklen gecacht. "
                    "Tipp: Sensor in der Integration konfigurieren, um Auto-Erkennung zu deaktivieren.",
                    state.entity_id,
                )
                return profile

        return None
