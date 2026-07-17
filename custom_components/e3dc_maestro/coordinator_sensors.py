"""Sensor state reading and unit normalisation."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ADDITIONAL_GENERATION_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_EVCC_CHARGING_ENTITY,
    CONF_EVCC_ENABLED,
    CONF_EVCC_MODE_ENTITY,
    CONF_GRID_POWER_INVERT,
    CONF_GRID_POWER_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_PV_FORECAST_ENABLED,
    CONF_PV_FORECAST_SENSOR,
    CONF_PV_FORECAST_TODAY_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_TOMORROW_PV_SENSOR,
    CONF_WALLBOX_INCLUDED_IN_HOUSE,
    CONF_WALLBOX_POWER_SENSOR,
)
from .control_engine import MaestroState

_LOGGER = logging.getLogger(__name__)


class CoordinatorSensorsMixin:
    _POWER_UNIT_TO_W: dict[str, float] = {
        "w": 1.0,
        "watt": 1.0,
        "watts": 1.0,
        "kw": 1000.0,
        "kilowatt": 1000.0,
        "mw": 1_000_000.0,
        "megawatt": 1_000_000.0,
    }


    def _read_sensors(self, opts: dict) -> MaestroState:
        soc = self._read_float(opts[CONF_SOC_SENSOR], required=True)
        pv = self._read_power_w(opts[CONF_PV_POWER_SENSOR], required=True)
        additional_generation = 0.0
        if opts.get(CONF_ADDITIONAL_GENERATION_SENSOR):
            additional_generation = self._read_power_w(
                opts[CONF_ADDITIONAL_GENERATION_SENSOR], required=False
            ) or 0.0
        house = self._read_power_w(opts[CONF_HOUSE_POWER_SENSOR], required=True)
        # Wallbox-Verbrauch separat (optional). Wenn der Hausverbrauchszähler die
        # Wallbox bereits enthält (typisch openWB am EVU-Zähler), ziehen wir sie
        # ab, damit die Optimierungs-Logik einen "reinen" Hausverbrauch sieht.
        wallbox = 0.0
        wb_sensor = opts.get(CONF_WALLBOX_POWER_SENSOR)
        if wb_sensor:
            wb_val = self._read_power_w(wb_sensor, required=False)
            if wb_val is not None:
                wallbox = max(0.0, wb_val)
                if opts.get(CONF_WALLBOX_INCLUDED_IN_HOUSE, False) and house is not None:
                    house = max(0.0, house - wallbox)
        grid = self._read_power_w(opts[CONF_GRID_POWER_SENSOR], required=True)
        if grid is not None and opts.get(CONF_GRID_POWER_INVERT, False):
            grid = -grid
        batt = self._read_power_w(opts[CONF_BATTERY_POWER_SENSOR], required=True)
        forecast: float | None = None
        if opts.get(CONF_PV_FORECAST_ENABLED) and opts.get(CONF_PV_FORECAST_SENSOR):
            forecast = self._read_float(opts[CONF_PV_FORECAST_SENSOR], required=False)

        # F1+: Forward-Looking inputs (morgen PV + Wochentags-Verbrauch)
        tomorrow_pv: float | None = None
        if self._params.forward_looking_enabled and opts.get(CONF_TOMORROW_PV_SENSOR):
            tomorrow_pv = self._read_float(
                opts[CONF_TOMORROW_PV_SENSOR], required=False
            )
        tomorrow_consumption: float | None = None
        if self._params.forward_looking_enabled and self._consumption_stats is not None:
            tomorrow_local = dt_util.now() + timedelta(days=1)
            tomorrow_consumption = self._consumption_stats.weekday_total_kwh(
                tomorrow_local.weekday()
            )

        # D1: EVCC state
        evcc_charging = False
        evcc_mode: str | None = None
        if opts.get(CONF_EVCC_ENABLED):
            if opts.get(CONF_EVCC_CHARGING_ENTITY):
                cs = self.hass.states.get(opts[CONF_EVCC_CHARGING_ENTITY])
                if cs and cs.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    evcc_charging = cs.state.lower() in ("true", "on", "1", "yes")
            if opts.get(CONF_EVCC_MODE_ENTITY):
                ms = self.hass.states.get(opts[CONF_EVCC_MODE_ENTITY])
                if ms and ms.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    evcc_mode = ms.state

        # Schwacher-PV-Tag: Tagesprognose + historischer Peak einlesen, latchen.
        today_pv_kwh, peak_pv_kwh = self._resolve_low_yield_inputs(opts)

        return MaestroState(
            soc=soc,
            pv_power=pv + additional_generation,
            house_power=house,
            grid_power=grid,
            battery_power=batt,
            pv_forecast_remaining_kwh=forecast,
            wallbox_power=wallbox,
            evcc_charging=evcc_charging,
            evcc_mode=evcc_mode,
            tomorrow_pv_kwh=tomorrow_pv,
            tomorrow_consumption_kwh=tomorrow_consumption,
            pv_forecast_today_kwh=today_pv_kwh,
            pv_stats_peak_kwh=peak_pv_kwh,
        )


    def _resolve_low_yield_inputs(
        self, opts: dict[str, Any]
    ) -> tuple[float | None, float | None]:
        """Lese Tagesprognose + historischen Peak; latch nur die Eingangswerte.

        Rückgabe ``(today_kwh, peak_kwh)`` für die ``MaestroState``-Felder.
        Die Tagesprognose wird einmal pro lokalem Tag festgehalten, damit
        Solcast-Updates den Tag nicht hin- und herschalten. Schwelle und
        Referenz-Parameter werden in ``_is_low_yield_day_active`` live
        ausgewertet.
        """
        if not self._params.low_yield_priority_enabled:
            self._low_yield_latch_date = None
            self._low_yield_stats_peak_kwh = None
            self._low_yield_today_kwh = None
            return (None, None)

        today_kwh: float | None = None
        sensor_id = opts.get(CONF_PV_FORECAST_TODAY_SENSOR)
        if sensor_id:
            today_kwh = self._read_float(sensor_id, required=False)

        peak_kwh: float | None = None
        if self._pv_stats is not None and self._pv_stats.data_days >= 7:
            peak_kwh = self._pv_stats.peak_daily_yield_kwh()

        # Latchen: nur einmal pro lokalem Tag aktualisieren. Vor dem ersten
        # validen Wert (z. B. direkt nach HA-Start ohne Solcast-Update) bleibt
        # der Latch leer und das Feature ist inaktiv.
        local_today = dt_util.now().date()
        if today_kwh is not None and today_kwh >= 0:
            if (
                self._low_yield_latch_date != local_today
                or self._low_yield_today_kwh is None
            ):
                self._low_yield_today_kwh = today_kwh
                self._low_yield_stats_peak_kwh = peak_kwh
                self._low_yield_latch_date = local_today

        return (self._low_yield_today_kwh, self._low_yield_stats_peak_kwh)


    def _read_float(self, entity_id: str, required: bool = False) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""):
            if required:
                raise ValueError(f"Entity '{entity_id}' nicht verfügbar")
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError) as err:
            if required:
                raise ValueError(f"Entity '{entity_id}' hat keinen numerischen Wert: {state.state}") from err
            return None


    def _read_power_w(self, entity_id: str, required: bool = False) -> float | None:
        """Read a power sensor and normalise the value to Watt.

        Auto-converts based on the entity's ``unit_of_measurement`` attribute
        (W / kW / MW). Falls back to W if the unit is missing or unknown so
        legacy configurations keep working. The detected unit is cached and
        only logged once per entity to avoid log spam.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""):
            if required:
                raise ValueError(f"Entity '{entity_id}' nicht verfügbar")
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError) as err:
            if required:
                raise ValueError(
                    f"Entity '{entity_id}' hat keinen numerischen Wert: {state.state}"
                ) from err
            return None
        unit = (state.attributes.get("unit_of_measurement") or "").strip().lower()
        factor = self._POWER_UNIT_TO_W.get(unit, 1.0)
        cache = self.__dict__.setdefault("_power_unit_cache", {})
        prev = cache.get(entity_id)
        if prev != (unit, factor):
            cache[entity_id] = (unit, factor)
            if unit and unit not in self._POWER_UNIT_TO_W:
                _LOGGER.warning(
                    "Power sensor '%s' has unknown unit '%s' – treating as W",
                    entity_id, unit,
                )
            elif factor != 1.0:
                _LOGGER.info(
                    "Power sensor '%s' liefert %s – wird automatisch in W umgerechnet (×%g)",
                    entity_id, unit, factor,
                )
        return value * factor
