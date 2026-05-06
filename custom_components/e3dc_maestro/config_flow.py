"""Config flow for E3DC Maestro."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADDITIONAL_GENERATION_SENSOR,
    CONF_ADVANCED_CORRIDOR,
    CONF_BATTERY_CHARGED_TODAY_SENSOR,
    CONF_BATTERY_DISCHARGED_TODAY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CHARGE_TARGET,
    CONF_CHARGE_THRESHOLD,
    CONF_CHEAP_THRESHOLD,
    CONF_DYNAMIC_TARIFF_ENABLED,
    CONF_FEED_IN_LIMIT_PERCENT,
    CONF_GRID_POWER_SENSOR,
    CONF_HP_ENABLED,
    CONF_HP_MAX_PRICE,
    CONF_HP_MIN_PAUSE_MINUTES,
    CONF_HP_MIN_RUN_MINUTES,
    CONF_HP_MIN_SURPLUS,
    CONF_HP_SERVICE_OFF,
    CONF_HP_SERVICE_ON,
    CONF_HP_SWITCH_ENTITY,
    CONF_HP_TIME_END,
    CONF_HP_TIME_START,
    CONF_HT_ENABLED,
    CONF_HT_MIN,
    CONF_HT_OFF,
    CONF_HT_ON,
    CONF_HT_SAT,
    CONF_HT_SOCKEL,
    CONF_HT_SUN,
    CONF_HOUSE_POWER_SENSOR,
    CONF_INSTALLED_KWP,
    CONF_INVERTER_POWER,
    CONF_LOWER_CORRIDOR,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_GRID_CHARGE_KWH,
    CONF_MIN_CHARGE_POWER,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_PRICE_SENSOR,
    CONF_PV_FORECAST_ENABLED,
    CONF_PV_FORECAST_SAFETY_FACTOR,
    CONF_PV_FORECAST_SENSOR,
    CONF_PV_FORECAST_THRESHOLD_KWH,
    CONF_DELAY_MIN_SOC,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SUMMER_CHARGE_END,
    CONF_SUMMER_MAXIMUM_HOUR,
    CONF_UPDATE_INTERVAL,
    CONF_UPPER_CORRIDOR,
    CONF_WALLBOX_ENABLED,
    CONF_WALLBOX_MAX_CURRENT,
    CONF_WALLBOX_MIN_CURRENT,
    CONF_WALLBOX_MIN_SURPLUS,
    CONF_WALLBOX_PHASES,
    CONF_WALLBOX_SERVICE_OFF,
    CONF_WALLBOX_SERVICE_ON,
    CONF_WALLBOX_TYPE,
    CONF_WATCHDOG_TIMEOUT,
    CONF_WINTER_MINIMUM_HOUR,
    DEFAULT_CHARGE_TARGET,
    DEFAULT_CHARGE_THRESHOLD,
    DEFAULT_CHEAP_THRESHOLD,
    DEFAULT_FEED_IN_LIMIT_PERCENT,
    DEFAULT_HP_MAX_PRICE,
    DEFAULT_HP_MIN_PAUSE_MINUTES,
    DEFAULT_HP_MIN_RUN_MINUTES,
    DEFAULT_HP_MIN_SURPLUS,
    DEFAULT_HT_MIN,
    DEFAULT_HT_OFF,
    DEFAULT_HT_ON,
    DEFAULT_HT_SOCKEL,
    DEFAULT_INSTALLED_KWP,
    DEFAULT_INVERTER_POWER,
    DEFAULT_LOWER_CORRIDOR,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_GRID_CHARGE_KWH,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_MIN_CHARGE_POWER,
    DEFAULT_PV_FORECAST_SAFETY_FACTOR,
    DEFAULT_PV_FORECAST_THRESHOLD_KWH,
    DEFAULT_DELAY_MIN_SOC,
    DEFAULT_SUMMER_CHARGE_END,
    DEFAULT_SUMMER_MAXIMUM_HOUR,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPPER_CORRIDOR,
    DEFAULT_WALLBOX_MAX_CURRENT,
    DEFAULT_WALLBOX_MIN_CURRENT,
    DEFAULT_WALLBOX_MIN_SURPLUS,
    DEFAULT_WALLBOX_PHASES,
    DEFAULT_WATCHDOG_TIMEOUT,
    DEFAULT_WINTER_MINIMUM_HOUR,
    DEFAULT_SOC_HYSTERESIS_PERCENT,
    DEFAULT_CHARGE_RAMP_W_PER_CYCLE,
    DEFAULT_RESERVE_WINTER_PERCENT,
    DEFAULT_RESERVE_EQUINOX_PERCENT,
    CONF_SOC_HYSTERESIS_PERCENT,
    CONF_CHARGE_RAMP_W_PER_CYCLE,
    CONF_SEASONAL_RESERVE_ENABLED,
    CONF_RESERVE_WINTER_PERCENT,
    CONF_RESERVE_EQUINOX_PERCENT,
    CONF_ADAPTIVE_RESERVE_ENABLED,
    CONF_ADAPTIVE_RESERVE_LOOKBACK_DAYS,
    CONF_ADAPTIVE_RESERVE_MIN_DAYS,
    CONF_ADAPTIVE_RESERVE_SAFETY_FACTOR,
    DEFAULT_ADAPTIVE_RESERVE_ENABLED,
    DEFAULT_ADAPTIVE_RESERVE_LOOKBACK_DAYS,
    DEFAULT_ADAPTIVE_RESERVE_MIN_DAYS,
    DEFAULT_ADAPTIVE_RESERVE_SAFETY_FACTOR,
    CONF_EVCC_ENABLED,
    CONF_EVCC_CHARGING_ENTITY,
    CONF_EVCC_MODE_ENTITY,
    CONF_EVCC_NOW_VALUE,
    DEFAULT_EVCC_NOW_VALUE,
    CONF_EVCC_DISCHARGE_LIMIT_W,
    DEFAULT_EVCC_DISCHARGE_LIMIT_W,
    CONF_SPREADING_ENABLED,
    CONF_SPREADING_TARGET_SOC,
    DEFAULT_SPREADING_TARGET_SOC,
    CONF_TARIFF_SLOTS,
    CONF_FORWARD_LOOKING_ENABLED,
    CONF_TOMORROW_PV_SENSOR,
    CONF_FORWARD_LOOKING_MAX_SOC,
    DEFAULT_FORWARD_LOOKING_ENABLED,
    DEFAULT_FORWARD_LOOKING_MAX_SOC,
    CONF_MORNING_CAP_ENABLED,
    CONF_MORNING_CAP_SOC,
    CONF_MORNING_CAP_UNTIL_H,
    CONF_GENTLE_CHARGE_ENABLED,
    CONF_GENTLE_CHARGE_FACTOR,
    DEFAULT_MORNING_CAP_ENABLED,
    DEFAULT_MORNING_CAP_SOC,
    DEFAULT_MORNING_CAP_UNTIL_H,
    DEFAULT_GENTLE_CHARGE_ENABLED,
    DEFAULT_GENTLE_CHARGE_FACTOR,
    CONF_AUTO_MODE_ENABLED,
    CONF_AUTO_MODE_OBJECTIVE,
    DEFAULT_AUTO_MODE_ENABLED,
    DEFAULT_AUTO_MODE_OBJECTIVE,
    AUTO_MODE_OBJECTIVES,
    DOMAIN,
    E3DC_RSCP_DOMAIN,
    WALLBOX_TYPE_E3DC,
    WALLBOX_TYPE_GENERIC,
)

_LOGGER = logging.getLogger(__name__)


def _entity_selector(domain: str = "sensor") -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain)
    )


def _number_selector(
    min_val: float, max_val: float, step: float = 1.0, unit: str | None = None
) -> selector.NumberSelector:
    del unit
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Step schemas
# ──────────────────────────────────────────────────────────────────────────────

STEP_SOURCES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOC_SENSOR): _entity_selector(),
        vol.Required(CONF_PV_POWER_SENSOR): _entity_selector(),
        vol.Optional(CONF_ADDITIONAL_GENERATION_SENSOR): _entity_selector(),
        vol.Required(CONF_HOUSE_POWER_SENSOR): _entity_selector(),
        vol.Required(CONF_GRID_POWER_SENSOR): _entity_selector(),
        vol.Required(CONF_BATTERY_POWER_SENSOR): _entity_selector(),
        vol.Optional(CONF_BATTERY_CHARGED_TODAY_SENSOR): _entity_selector(),
        vol.Optional(CONF_BATTERY_DISCHARGED_TODAY_SENSOR): _entity_selector(),
    }
)

STEP_SYSTEM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INVERTER_POWER, default=DEFAULT_INVERTER_POWER): _number_selector(1000, 30000, 100, "W"),
        vol.Required(CONF_MAX_CHARGE_POWER, default=DEFAULT_MAX_CHARGE_POWER): _number_selector(500, 15000, 100, "W"),
        vol.Required(CONF_MIN_CHARGE_POWER, default=DEFAULT_MIN_CHARGE_POWER): _number_selector(50, 5000, 50, "W"),
        vol.Required(CONF_INSTALLED_KWP, default=DEFAULT_INSTALLED_KWP): _number_selector(0.5, 100.0, 0.5, "kWp"),
        vol.Required(CONF_FEED_IN_LIMIT_PERCENT, default=DEFAULT_FEED_IN_LIMIT_PERCENT): _number_selector(0, 100, 1, "%"),
        vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): _number_selector(10, 120, 5, "s"),
        vol.Optional(CONF_ADVANCED_CORRIDOR, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_LOWER_CORRIDOR, default=DEFAULT_LOWER_CORRIDOR): _number_selector(0, 5000, 50, "W"),
        vol.Optional(CONF_UPPER_CORRIDOR, default=DEFAULT_UPPER_CORRIDOR): _number_selector(0, 15000, 50, "W"),
        vol.Optional(CONF_SOC_HYSTERESIS_PERCENT, default=DEFAULT_SOC_HYSTERESIS_PERCENT): _number_selector(0, 10, 0.5, "%"),
        vol.Optional(CONF_CHARGE_RAMP_W_PER_CYCLE, default=DEFAULT_CHARGE_RAMP_W_PER_CYCLE): _number_selector(0, 2000, 50, "W"),
    }
)

STEP_SEASON_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGE_THRESHOLD, default=DEFAULT_CHARGE_THRESHOLD): _number_selector(0, 50, 1, "%"),
        vol.Required(CONF_CHARGE_TARGET, default=DEFAULT_CHARGE_TARGET): _number_selector(50, 100, 1, "%"),
        vol.Required(CONF_WINTER_MINIMUM_HOUR, default=DEFAULT_WINTER_MINIMUM_HOUR): _number_selector(6, 18, 0.5, "h"),
        vol.Required(CONF_SUMMER_MAXIMUM_HOUR, default=DEFAULT_SUMMER_MAXIMUM_HOUR): _number_selector(8, 20, 0.5, "h"),
        vol.Required(CONF_SUMMER_CHARGE_END, default=DEFAULT_SUMMER_CHARGE_END): _number_selector(12, 23, 0.5, "h"),
        vol.Optional(CONF_SEASONAL_RESERVE_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_RESERVE_WINTER_PERCENT, default=DEFAULT_RESERVE_WINTER_PERCENT): _number_selector(0, 80, 1, "%"),
        vol.Optional(CONF_RESERVE_EQUINOX_PERCENT, default=DEFAULT_RESERVE_EQUINOX_PERCENT): _number_selector(0, 50, 1, "%"),
        vol.Optional(CONF_ADAPTIVE_RESERVE_ENABLED, default=DEFAULT_ADAPTIVE_RESERVE_ENABLED): selector.BooleanSelector(),
        vol.Optional(CONF_ADAPTIVE_RESERVE_LOOKBACK_DAYS, default=DEFAULT_ADAPTIVE_RESERVE_LOOKBACK_DAYS): _number_selector(1, 60, 1, "d"),
        vol.Optional(CONF_ADAPTIVE_RESERVE_MIN_DAYS, default=DEFAULT_ADAPTIVE_RESERVE_MIN_DAYS): _number_selector(1, 30, 1, "d"),
        vol.Optional(CONF_ADAPTIVE_RESERVE_SAFETY_FACTOR, default=DEFAULT_ADAPTIVE_RESERVE_SAFETY_FACTOR): _number_selector(1.0, 3.0, 0.05, "x"),
    }
)

STEP_HT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HT_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_HT_ON, default=DEFAULT_HT_ON): _number_selector(0, 23, 1, "h"),
        vol.Optional(CONF_HT_OFF, default=DEFAULT_HT_OFF): _number_selector(0, 23, 1, "h"),
        vol.Optional(CONF_HT_MIN, default=DEFAULT_HT_MIN): _number_selector(0, 100, 1, "%"),
        vol.Optional(CONF_HT_SOCKEL, default=DEFAULT_HT_SOCKEL): _number_selector(0, 100, 1, "%"),
        vol.Optional(CONF_HT_SAT, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_HT_SUN, default=True): selector.BooleanSelector(),
    }
)

STEP_TARIFF_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DYNAMIC_TARIFF_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_PRICE_SENSOR): _entity_selector(),
        vol.Optional(CONF_CHEAP_THRESHOLD, default=DEFAULT_CHEAP_THRESHOLD): _number_selector(0.0, 1.0, 0.01, "€/kWh"),
        vol.Optional(CONF_MAX_GRID_CHARGE_KWH, default=DEFAULT_MAX_GRID_CHARGE_KWH): _number_selector(0, 20, 0.5, "kWh"),
    }
)

STEP_WALLBOX_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WALLBOX_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_WALLBOX_TYPE, default=WALLBOX_TYPE_E3DC): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[WALLBOX_TYPE_E3DC, WALLBOX_TYPE_GENERIC],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_WALLBOX_MIN_CURRENT, default=DEFAULT_WALLBOX_MIN_CURRENT): _number_selector(6, 32, 1, "A"),
        vol.Optional(CONF_WALLBOX_MAX_CURRENT, default=DEFAULT_WALLBOX_MAX_CURRENT): _number_selector(6, 32, 1, "A"),
        vol.Optional(CONF_WALLBOX_PHASES, default=DEFAULT_WALLBOX_PHASES): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["1", "3"], mode=selector.SelectSelectorMode.DROPDOWN)
        ),
        vol.Optional(CONF_WALLBOX_MIN_SURPLUS, default=DEFAULT_WALLBOX_MIN_SURPLUS): _number_selector(0, 10000, 100, "W"),
        vol.Optional(CONF_WALLBOX_SERVICE_ON): selector.ActionSelector(),
        vol.Optional(CONF_WALLBOX_SERVICE_OFF): selector.ActionSelector(),
    }
)

STEP_EVCC_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EVCC_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_EVCC_CHARGING_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "sensor", "input_boolean"])
        ),
        vol.Optional(CONF_EVCC_MODE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "input_select", "select"])
        ),
        vol.Optional(CONF_EVCC_NOW_VALUE, default=DEFAULT_EVCC_NOW_VALUE): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Optional(CONF_EVCC_DISCHARGE_LIMIT_W, default=DEFAULT_EVCC_DISCHARGE_LIMIT_W): _number_selector(0, 15000, 50, "W"),
    }
)

STEP_HP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HP_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_HP_SWITCH_ENTITY): _entity_selector("switch"),
        vol.Optional(CONF_HP_SERVICE_ON): selector.ActionSelector(),
        vol.Optional(CONF_HP_SERVICE_OFF): selector.ActionSelector(),
        vol.Optional(CONF_HP_MIN_SURPLUS, default=DEFAULT_HP_MIN_SURPLUS): _number_selector(0, 10000, 100, "W"),
        vol.Optional(CONF_HP_MAX_PRICE, default=DEFAULT_HP_MAX_PRICE): _number_selector(0, 1.0, 0.01, "€/kWh"),
        vol.Optional(CONF_HP_TIME_START, default="06:00"): selector.TimeSelector(),
        vol.Optional(CONF_HP_TIME_END, default="22:00"): selector.TimeSelector(),
        vol.Optional(CONF_HP_MIN_RUN_MINUTES, default=DEFAULT_HP_MIN_RUN_MINUTES): _number_selector(0, 120, 5, "min"),
        vol.Optional(CONF_HP_MIN_PAUSE_MINUTES, default=DEFAULT_HP_MIN_PAUSE_MINUTES): _number_selector(0, 120, 5, "min"),
    }
)

STEP_FAILSAFE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_WATCHDOG_TIMEOUT, default=DEFAULT_WATCHDOG_TIMEOUT): _number_selector(0, 60, 1, "min"),
    }
)

STEP_PV_FORECAST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PV_FORECAST_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_PV_FORECAST_SENSOR): _entity_selector(),
        vol.Optional(
            CONF_PV_FORECAST_THRESHOLD_KWH, default=DEFAULT_PV_FORECAST_THRESHOLD_KWH
        ): _number_selector(0, 100, 0.5, "kWh"),
        vol.Optional(
            CONF_BATTERY_CAPACITY_KWH, default=DEFAULT_BATTERY_CAPACITY_KWH
        ): _number_selector(1, 100, 0.5, "kWh"),
        vol.Optional(
            CONF_PV_FORECAST_SAFETY_FACTOR, default=DEFAULT_PV_FORECAST_SAFETY_FACTOR
        ): _number_selector(1.0, 3.0, 0.05),
        vol.Optional(
            CONF_DELAY_MIN_SOC, default=DEFAULT_DELAY_MIN_SOC
        ): _number_selector(0, 80, 5, "%"),
        vol.Optional(CONF_SPREADING_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(
            CONF_SPREADING_TARGET_SOC, default=DEFAULT_SPREADING_TARGET_SOC
        ): _number_selector(50, 100, 1, "%"),
        # F1+: Forward-Looking (vorausschauende Ladung)
        vol.Optional(
            CONF_FORWARD_LOOKING_ENABLED, default=DEFAULT_FORWARD_LOOKING_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(CONF_TOMORROW_PV_SENSOR): _entity_selector(),
        vol.Optional(
            CONF_FORWARD_LOOKING_MAX_SOC, default=DEFAULT_FORWARD_LOOKING_MAX_SOC
        ): _number_selector(60, 100, 1, "%"),
    }
)
STEP_FLAT_CURVE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_MORNING_CAP_ENABLED, default=DEFAULT_MORNING_CAP_ENABLED): selector.BooleanSelector(),
        vol.Optional(
            CONF_MORNING_CAP_SOC, default=DEFAULT_MORNING_CAP_SOC
        ): _number_selector(10, 80, 5, "%"),
        vol.Optional(
            CONF_MORNING_CAP_UNTIL_H, default=DEFAULT_MORNING_CAP_UNTIL_H
        ): _number_selector(0, 14, 0.5, "h"),
        vol.Optional(CONF_GENTLE_CHARGE_ENABLED, default=DEFAULT_GENTLE_CHARGE_ENABLED): selector.BooleanSelector(),
        vol.Optional(
            CONF_GENTLE_CHARGE_FACTOR, default=DEFAULT_GENTLE_CHARGE_FACTOR
        ): _number_selector(0.05, 1.0, 0.05),
    }
)
STEP_AUTO_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AUTO_MODE_ENABLED, default=DEFAULT_AUTO_MODE_ENABLED): selector.BooleanSelector(),
        vol.Optional(
            CONF_AUTO_MODE_OBJECTIVE, default=DEFAULT_AUTO_MODE_OBJECTIVE
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=o, label=o)
                    for o in AUTO_MODE_OBJECTIVES
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

# ──────────────────────────────────────────────────────────────────────────────
# Phase C: Tariff slot list management (Mixin)
# ──────────────────────────────────────────────────────────────────────────────

_TARIFF_CLASSES = ["high", "low", "normal"]
_WEEKDAY_VALUES = ["0", "1", "2", "3", "4", "5", "6"]
_WEEKDAY_LABELS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _slot_edit_schema(defaults: dict[str, Any]) -> vol.Schema:
    weekday_options = [
        selector.SelectOptionDict(value=v, label=l)
        for v, l in zip(_WEEKDAY_VALUES, _WEEKDAY_LABELS_DE)
    ]
    weekdays_default = [str(d) for d in defaults.get("weekdays", [0, 1, 2, 3, 4])]
    schema_dict: dict[Any, Any] = {
        vol.Required("weekdays", default=weekdays_default): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=weekday_options,
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Required("start_h", default=float(defaults.get("start_h", 5))): _number_selector(0, 24, 0.25, "h"),
        vol.Required("end_h", default=float(defaults.get("end_h", 21))): _number_selector(0, 24, 0.25, "h"),
        vol.Required("class_", default=defaults.get("class_", "high")): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_TARIFF_CLASSES, mode=selector.SelectSelectorMode.DROPDOWN
            )
        ),
    }
    reserve_default = defaults.get("min_reserve_soc")
    if reserve_default is None:
        schema_dict[vol.Optional("min_reserve_soc")] = _number_selector(0, 100, 1, "%")
    else:
        schema_dict[
            vol.Optional("min_reserve_soc", default=float(reserve_default))
        ] = _number_selector(0, 100, 1, "%")
    return vol.Schema(schema_dict)


def _format_slots_for_display(slots: list[dict[str, Any]]) -> str:
    """Render a human-readable summary of the current slot list."""
    if not slots:
        return "(keine Slots konfiguriert – HT/Tibber-Felder werden als Fallback verwendet)"
    lines = []
    for i, s in enumerate(slots):
        wd = sorted(int(d) for d in s.get("weekdays", []))
        wd_str = ",".join(_WEEKDAY_LABELS_DE[d] for d in wd if 0 <= d <= 6)
        reserve = s.get("min_reserve_soc")
        reserve_str = f", reserve≥{reserve:g}%" if reserve is not None else ""
        lines.append(
            f"{i}: [{wd_str}] {s.get('start_h', 0):g}–{s.get('end_h', 0):g}h "
            f"({s.get('class_', 'high')}{reserve_str})"
        )
    return "\n".join(lines)


class _TariffSlotsMixin:
    """Slot-list management shared by ConfigFlow and OptionsFlow.

    Subclasses must implement ``_slot_state()`` returning the dict that
    carries the in-progress options (``self._data`` or ``self._options``)
    and ``_after_slots_step()`` returning the coroutine for the next step.
    """

    _editing_slot_idx: int | None = None

    def _slot_state(self) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def _after_slots_step(self):  # pragma: no cover - abstract
        raise NotImplementedError

    async def async_step_tariff_slots(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = self._slot_state()
        slots: list[dict[str, Any]] = list(state.get(CONF_TARIFF_SLOTS, []))

        if user_input is not None:
            action = user_input.get("action", "done")
            if action == "done":
                state[CONF_TARIFF_SLOTS] = slots
                return await self._after_slots_step()
            if action == "add":
                self._editing_slot_idx = None
                return await self.async_step_tariff_slot_edit()
            if action.startswith("edit_"):
                idx = int(action.split("_", 1)[1])
                if 0 <= idx < len(slots):
                    self._editing_slot_idx = idx
                    return await self.async_step_tariff_slot_edit()
            if action.startswith("remove_"):
                idx = int(action.split("_", 1)[1])
                if 0 <= idx < len(slots):
                    slots.pop(idx)
                    state[CONF_TARIFF_SLOTS] = slots
                return await self.async_step_tariff_slots()

        # Build action options dynamically from the current slot list.
        actions: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value="add", label="➕ Slot hinzufügen"),
        ]
        for i in range(len(slots)):
            actions.append(
                selector.SelectOptionDict(value=f"edit_{i}", label=f"✏️  Slot {i} bearbeiten")
            )
            actions.append(
                selector.SelectOptionDict(value=f"remove_{i}", label=f"🗑  Slot {i} entfernen")
            )
        actions.append(selector.SelectOptionDict(value="done", label="✅ Fertig"))

        schema = vol.Schema(
            {
                vol.Required("action", default="done"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=actions, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="tariff_slots",
            data_schema=schema,
            description_placeholders={"slots": _format_slots_for_display(slots)},
        )

    async def async_step_tariff_slot_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = self._slot_state()
        slots: list[dict[str, Any]] = list(state.get(CONF_TARIFF_SLOTS, []))

        if user_input is not None:
            new_slot: dict[str, Any] = {
                "weekdays": sorted(int(d) for d in user_input.get("weekdays", [])),
                "start_h": float(user_input["start_h"]),
                "end_h": float(user_input["end_h"]),
                "class_": user_input.get("class_", "high"),
            }
            reserve = user_input.get("min_reserve_soc")
            if reserve is not None:
                new_slot["min_reserve_soc"] = float(reserve)

            if self._editing_slot_idx is None:
                slots.append(new_slot)
            elif 0 <= self._editing_slot_idx < len(slots):
                slots[self._editing_slot_idx] = new_slot
            state[CONF_TARIFF_SLOTS] = slots
            self._editing_slot_idx = None
            return await self.async_step_tariff_slots()

        if self._editing_slot_idx is not None and 0 <= self._editing_slot_idx < len(slots):
            defaults = slots[self._editing_slot_idx]
        else:
            defaults = {"weekdays": [0, 1, 2, 3, 4], "start_h": 5, "end_h": 21, "class_": "high"}

        return self.async_show_form(
            step_id="tariff_slot_edit",
            data_schema=_slot_edit_schema(defaults),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Config Flow
# ──────────────────────────────────────────────────────────────────────────────

class E3DCMaestroConfigFlow(_TariffSlotsMixin, ConfigFlow, domain=DOMAIN):
    """Multi-step config flow for E3DC Maestro."""

    VERSION = 2
    _data: dict[str, Any] = {}

    def _slot_state(self) -> dict[str, Any]:
        return self._data

    async def _after_slots_step(self):
        return await self.async_step_tariff()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 0: guard – check e3dc_rscp is present."""
        if not self.hass.config_entries.async_entries(E3DC_RSCP_DOMAIN):
            return self.async_abort(reason="e3dc_rscp_not_configured")
        return await self.async_step_sources()

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 1: Select source entities."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_system()
        return self.async_show_form(step_id="sources", data_schema=STEP_SOURCES_SCHEMA)

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: System parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_season()
        return self.async_show_form(step_id="system", data_schema=STEP_SYSTEM_SCHEMA)

    async def async_step_season(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 3: Season & corridor settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_pv_forecast()
        return self.async_show_form(step_id="season", data_schema=STEP_SEASON_SCHEMA)

    async def async_step_pv_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 3b: PV forecast / charge delay."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_ht()
        return self.async_show_form(step_id="pv_forecast", data_schema=STEP_PV_FORECAST_SCHEMA)

    async def async_step_ht(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 4: HT/NT peak protection."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_tariff_slots()
        return self.async_show_form(step_id="ht", data_schema=STEP_HT_SCHEMA)

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 5: Dynamic tariff settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_wallbox()
        return self.async_show_form(step_id="tariff", data_schema=STEP_TARIFF_SCHEMA)

    async def async_step_wallbox(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 6: Wallbox settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_evcc()
        return self.async_show_form(step_id="wallbox", data_schema=STEP_WALLBOX_SCHEMA)

    async def async_step_evcc(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 6b: EVCC integration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_heatpump()
        return self.async_show_form(step_id="evcc", data_schema=STEP_EVCC_SCHEMA)

    async def async_step_heatpump(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 7: Heat pump settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_failsafe()
        return self.async_show_form(step_id="heatpump", data_schema=STEP_HP_SCHEMA)

    async def async_step_failsafe(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 8: Failsafe settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_flat_curve()
        return self.async_show_form(step_id="failsafe", data_schema=STEP_FAILSAFE_SCHEMA)

    async def async_step_flat_curve(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 9: F0 Morning-Cap + Gentle-Charge."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_auto_mode()
        return self.async_show_form(step_id="flat_curve", data_schema=STEP_FLAT_CURVE_SCHEMA)

    async def async_step_auto_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 10: F3 Auto-Optimierungs-Modus."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="E3DC Maestro", data={}, options=self._data)
        return self.async_show_form(step_id="auto_mode", data_schema=STEP_AUTO_MODE_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return E3DCMaestroOptionsFlow()


# ──────────────────────────────────────────────────────────────────────────────
# Options Flow (re-uses the same step schemas)
# ──────────────────────────────────────────────────────────────────────────────

class E3DCMaestroOptionsFlow(_TariffSlotsMixin, OptionsFlow):
    """Options flow mirrors steps 1-8 for live re-configuration."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    def _slot_state(self) -> dict[str, Any]:
        return self._options

    async def _after_slots_step(self):
        return await self.async_step_tariff()

    def _prefilled(self, schema: vol.Schema) -> vol.Schema:
        """Return schema with current option values as defaults."""
        return self.add_suggested_values_to_schema(schema, self._options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # Load current options on first call (self.config_entry available from HA 2023.9+)
        self._options = dict(self.config_entry.options)
        return await self.async_step_sources(user_input)

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_system()
        return self.async_show_form(step_id="sources", data_schema=self._prefilled(STEP_SOURCES_SCHEMA))

    async def async_step_system(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_season()
        return self.async_show_form(step_id="system", data_schema=self._prefilled(STEP_SYSTEM_SCHEMA))

    async def async_step_season(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_pv_forecast()
        return self.async_show_form(step_id="season", data_schema=self._prefilled(STEP_SEASON_SCHEMA))

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_ht()
        return self.async_show_form(step_id="pv_forecast", data_schema=self._prefilled(STEP_PV_FORECAST_SCHEMA))

    async def async_step_ht(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_tariff_slots()
        return self.async_show_form(step_id="ht", data_schema=self._prefilled(STEP_HT_SCHEMA))

    async def async_step_tariff(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_wallbox()
        return self.async_show_form(step_id="tariff", data_schema=self._prefilled(STEP_TARIFF_SCHEMA))

    async def async_step_wallbox(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_evcc()
        return self.async_show_form(step_id="wallbox", data_schema=self._prefilled(STEP_WALLBOX_SCHEMA))

    async def async_step_evcc(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_heatpump()
        return self.async_show_form(step_id="evcc", data_schema=self._prefilled(STEP_EVCC_SCHEMA))

    async def async_step_heatpump(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_failsafe()
        return self.async_show_form(step_id="heatpump", data_schema=self._prefilled(STEP_HP_SCHEMA))

    async def async_step_failsafe(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_flat_curve()
        return self.async_show_form(step_id="failsafe", data_schema=self._prefilled(STEP_FAILSAFE_SCHEMA))

    async def async_step_flat_curve(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_auto_mode()
        return self.async_show_form(step_id="flat_curve", data_schema=self._prefilled(STEP_FLAT_CURVE_SCHEMA))

    async def async_step_auto_mode(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(step_id="auto_mode", data_schema=self._prefilled(STEP_AUTO_MODE_SCHEMA))
