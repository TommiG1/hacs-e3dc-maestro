"""Price plan (shadow mode): compute and cache the price-based charge/hold plan."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import CONF_PRICE_SENSOR
from .control_engine import (
    adaptive_emergency_reserve_soc as _adaptive_emergency_reserve_soc,
    seasonal_reserve_soc as _seasonal_reserve_soc,
)
from .price_curve import read_price_horizon
from .price_plan_runner import PricePlanSnapshot, compute_price_plan

if TYPE_CHECKING:
    from .control_engine import MaestroState

_LOGGER = logging.getLogger(__name__)


class CoordinatorPricePlanMixin:
    price_plan: PricePlanSnapshot | None = None
    _price_plan_fingerprint: tuple | None = None

    def _reset_price_plan(self) -> None:
        self.price_plan = None
        self._price_plan_fingerprint = None

    async def _async_update_price_plan(self, state: MaestroState, now: datetime) -> None:
        """Shadow mode: compute the plan, never touch the battery."""
        params = self._params
        if not params.price_plan_enabled:
            if self.price_plan is not None:
                self._reset_price_plan()
            return
        try:
            sensor_id = self.entry.options.get(CONF_PRICE_SENSOR)
            attrs: dict = {}
            if sensor_id:
                st = self.hass.states.get(sensor_id)
                if st is not None and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    attrs = dict(st.attributes)
            horizon = read_price_horizon(attrs, now)

            # Floor = max(Ladeschwelle, Notstromreserve)
            reserve = 0.0
            if params.seasonal_reserve_enabled:
                adaptive = _adaptive_emergency_reserve_soc(state, params)
                reserve = adaptive if adaptive is not None else _seasonal_reserve_soc(now, params)
            floor_pct = max(float(params.charge_threshold), float(reserve))

            cons_stats = getattr(self, "_consumption_stats", None)
            pv_stats = getattr(self, "_pv_stats", None)
            cons_profile = list(cons_stats.hourly_profile_w) if cons_stats is not None else None
            pv_hist = list(pv_stats.hourly_profile_w) if pv_stats is not None else None
            pv_today = self._read_pv_forecast_profile(now, days_ahead=0, ignore_enabled=True)
            pv_tomorrow = self._read_pv_forecast_profile(now, days_ahead=1, ignore_enabled=True)

            cap = max(float(params.battery_capacity_kwh), 0.1)
            cycles = max(float(getattr(params, "battery_total_cycles", 5000.0)), 100.0)
            capex = max(float(getattr(params, "battery_capex_eur", 8000.0)), 0.0)
            wear = capex / (cycles * 2.0 * cap)
            charged_today = float(self.stats.get("grid_to_battery_today_kwh", 0.0))

            # Re-plan every 5 min (slot boundaries move "now") or when inputs change.
            fingerprint = (
                (now.date(), now.hour, now.minute // 5),
                round(state.soc),
                tuple(horizon.prices) if horizon else None,
                round(charged_today, 1),
                round(floor_pct),
                params.price_plan_max_soc, params.price_plan_min_spread,
                params.price_plan_efficiency, params.price_plan_safety_factor,
                params.max_grid_charge_kwh, params.battery_capacity_kwh,
            )
            if fingerprint == self._price_plan_fingerprint and self.price_plan is not None:
                return

            def _run() -> PricePlanSnapshot:
                return compute_price_plan(
                    horizon=horizon,
                    now=now,
                    soc_pct=state.soc,
                    capacity_kwh=cap,
                    floor_pct=floor_pct,
                    ceiling_pct=float(params.price_plan_max_soc),
                    max_charge_kw=max(float(params.max_charge_power), 100.0) / 1000.0,
                    max_discharge_kw=max(float(params.inverter_power), 100.0) / 1000.0,
                    budget_per_day_kwh=float(params.max_grid_charge_kwh),
                    grid_charged_today_kwh=charged_today,
                    efficiency=float(params.price_plan_efficiency),
                    min_spread=float(params.price_plan_min_spread),
                    safety_factor=float(params.price_plan_safety_factor),
                    wear_eur_per_kwh=wear,
                    feed_in_price=float(params.feed_in_price),
                    cons_profile_w=cons_profile,
                    house_power_w=float(state.house_power),
                    pv_today_w=pv_today,
                    pv_tomorrow_w=pv_tomorrow,
                    pv_hist_w=pv_hist,
                )

            snapshot = await self.hass.async_add_executor_job(_run)
            self.price_plan = snapshot
            self._price_plan_fingerprint = fingerprint
            _LOGGER.debug("Preisplan: %s", snapshot.message)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Preisplan fehlgeschlagen: %s", err)
