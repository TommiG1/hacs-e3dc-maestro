"""Config flow for E3DC Maestro."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

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
    CONF_FIXED_BUY_PRICE,
    CONF_FEED_IN_PRICE,
    CONF_BATTERY_CAPEX_EUR,
    CONF_BATTERY_TOTAL_CYCLES,
    CONF_TARIFF_MODE,
    CONF_GRID_POWER_SENSOR,
    CONF_GRID_POWER_INVERT,
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
    CONF_PV_FORECAST_SENSOR_DAY2,
    CONF_PV_FORECAST_TODAY_SENSOR,
    CONF_PV_FORECAST_THRESHOLD_KWH,
    CONF_DELAY_MIN_SOC,
    CONF_LOW_YIELD_PRIORITY_ENABLED,
    CONF_LOW_YIELD_THRESHOLD,
    CONF_LOW_YIELD_REFERENCE_KWH,
    CONF_LOW_YIELD_REFERENCE_KWH_PER_KWP,
    DEFAULT_LOW_YIELD_PRIORITY_ENABLED,
    DEFAULT_LOW_YIELD_THRESHOLD,
    DEFAULT_LOW_YIELD_REFERENCE_KWH,
    DEFAULT_LOW_YIELD_REFERENCE_KWH_PER_KWP,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SUMMER_CHARGE_END,
    CONF_SUMMER_MAXIMUM_HOUR,
    CONF_UPDATE_INTERVAL,
    CONF_UPPER_CORRIDOR,
    CONF_WALLBOX_ENABLED,
    CONF_WALLBOX_INCLUDED_IN_HOUSE,
    CONF_WALLBOX_MAX_CURRENT,
    CONF_WALLBOX_MIN_CURRENT,
    CONF_WALLBOX_MIN_SURPLUS,
    CONF_WALLBOX_PHASES,
    CONF_WALLBOX_POWER_SENSOR,
    CONF_WALLBOX_PROVIDER,
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
    DEFAULT_TARIFF_MODE,
    DEFAULT_FIXED_BUY_PRICE,
    DEFAULT_FEED_IN_PRICE,
    DEFAULT_BATTERY_CAPEX_EUR,
    DEFAULT_BATTERY_TOTAL_CYCLES,
    TARIFF_MODES,
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
    CONF_ADAPTIVE_RESERVE_MAX_SOC,
    DEFAULT_ADAPTIVE_RESERVE_ENABLED,
    DEFAULT_ADAPTIVE_RESERVE_LOOKBACK_DAYS,
    DEFAULT_ADAPTIVE_RESERVE_MIN_DAYS,
    DEFAULT_ADAPTIVE_RESERVE_SAFETY_FACTOR,
    DEFAULT_ADAPTIVE_RESERVE_MAX_SOC,
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
    # Sizing Advisor
    CONF_SIZING_PV_ENERGY_SENSOR,
    CONF_SIZING_HOUSE_ENERGY_SENSOR,
    CONF_SIZING_HOUSE_FROM_BALANCE,
    DEFAULT_SIZING_HOUSE_FROM_BALANCE,
    CONF_SIZING_IMPORT_FROM_ENERGY_DASHBOARD,
    CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
    CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
    CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
    CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
    CONF_SIZING_WALLBOX_ENERGY_SENSOR,
    CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR,
    CONF_SIZING_ANALYSIS_DAYS,
    CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH,
    CONF_SIZING_FEED_IN_PRICE_EUR_KWH,
    CONF_SIZING_BATTERY_PRICE_EUR_KWH,
    CONF_SIZING_PV_PRICE_EUR_PER_KWP,
    CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR,
    CONF_SIZING_ROUND_TRIP_EFFICIENCY,
    CONF_SIZING_MAX_BATTERY_SWEEP_KWH,
    CONF_SIZING_BATTERY_STEP_KWH,
    CONF_SIZING_MAX_PV_EXPANSION_KWP,
    CONF_SIZING_PV_STEP_KWP,
    DEFAULT_SIZING_ANALYSIS_DAYS,
    DEFAULT_SIZING_ELECTRICITY_PRICE,
    DEFAULT_SIZING_FEED_IN_PRICE,
    DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH,
    DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP,
    DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR,
    DEFAULT_SIZING_ROUND_TRIP_EFFICIENCY,
    DEFAULT_SIZING_MAX_BATTERY_SWEEP_KWH,
    DEFAULT_SIZING_BATTERY_STEP_KWH,
    DEFAULT_SIZING_MAX_PV_EXPANSION_KWP,
    DEFAULT_SIZING_PV_STEP_KWP,
    DOMAIN,
    E3DC_RSCP_DOMAIN,
    WALLBOX_TYPE_E3DC,
    WALLBOX_TYPE_GENERIC,
    WALLBOX_PROVIDERS,
    WALLBOX_PROVIDER_E3DC,
    WALLBOX_PROVIDER_OPENWB,
    DEFAULT_WALLBOX_PROVIDER,
    DEFAULT_WALLBOX_INCLUDED_IN_HOUSE,
)

_LOGGER = logging.getLogger(__name__)

# ── Sizing Advisor schema ─────────────────────────────────────────────────────

STEP_SIZING_ADVISOR_SCHEMA = vol.Schema(
    {
        # Energy sensors (HA Energy Dashboard / total_increasing)
        # PV accepts multiple sensors (multi-inverter setups)
        vol.Optional(CONF_SIZING_PV_ENERGY_SENSOR, default=[]): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", multiple=True)
        ),
        # Single-entity selectors: no default — EntitySelector rejects empty
        # strings as invalid entity IDs.  Omitting the field is allowed.
        vol.Optional(CONF_SIZING_HOUSE_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        # Wenn aktiv, wird der ggf. gesetzte Haus-Sensor ignoriert und die
        # Hauslast aus der Energiebilanz abgeleitet (pv + grid_in + batt_d -
        # grid_out - batt_c).
        vol.Optional(
            CONF_SIZING_HOUSE_FROM_BALANCE,
            default=DEFAULT_SIZING_HOUSE_FROM_BALANCE,
        ): selector.BooleanSelector(),
        # Volatile: beim Speichern werden alle Sensor-Felder aus dem
        # HA Energy Dashboard neu eingelesen (überschreibt bestehende Werte).
        # Wird nicht persistiert – beim nächsten Aufruf immer deaktiviert.
        vol.Optional(
            CONF_SIZING_IMPORT_FROM_ENERGY_DASHBOARD,
            default=False,
        ): selector.BooleanSelector(),
        vol.Optional(CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SIZING_WALLBOX_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        # Analysis parameters
        vol.Optional(CONF_SIZING_ANALYSIS_DAYS, default=DEFAULT_SIZING_ANALYSIS_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=30, max=730)
        ),
        vol.Optional(CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH, default=DEFAULT_SIZING_ELECTRICITY_PRICE): vol.All(
            vol.Coerce(float), vol.Range(min=0.05, max=2.0)
        ),
        vol.Optional(CONF_SIZING_FEED_IN_PRICE_EUR_KWH, default=DEFAULT_SIZING_FEED_IN_PRICE): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=1.0)
        ),
        vol.Optional(CONF_SIZING_BATTERY_PRICE_EUR_KWH, default=DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH): vol.All(
            vol.Coerce(float), vol.Range(min=100.0, max=5000.0)
        ),
        vol.Optional(CONF_SIZING_PV_PRICE_EUR_PER_KWP, default=DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP): vol.All(
            vol.Coerce(float), vol.Range(min=200.0, max=5000.0)
        ),
        vol.Optional(CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR, default=DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=20000.0)
        ),
        vol.Optional(CONF_SIZING_ROUND_TRIP_EFFICIENCY, default=DEFAULT_SIZING_ROUND_TRIP_EFFICIENCY): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=1.0)
        ),
        vol.Optional(CONF_SIZING_MAX_BATTERY_SWEEP_KWH, default=DEFAULT_SIZING_MAX_BATTERY_SWEEP_KWH): vol.All(
            vol.Coerce(float), vol.Range(min=5.0, max=200.0)
        ),
        vol.Optional(CONF_SIZING_BATTERY_STEP_KWH, default=DEFAULT_SIZING_BATTERY_STEP_KWH): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=10.0)
        ),
        vol.Optional(CONF_SIZING_MAX_PV_EXPANSION_KWP, default=DEFAULT_SIZING_MAX_PV_EXPANSION_KWP): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=200.0)
        ),
        vol.Optional(CONF_SIZING_PV_STEP_KWP, default=DEFAULT_SIZING_PV_STEP_KWP): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=10.0)
        ),
    }
)


def _entity_selector(domain: str = "sensor") -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain)
    )


# RSCP-Suffix-Mapping (E3DC RSCP Integration von Torben Nehmer).
# Der Präfix ist gerätenamen-abhängig (z. B. sensor.s10e_pro_, sensor.s10_*),
# der Suffix ist bei der Integration stabil.
_RSCP_SUFFIX_MAP: dict[str, str] = {
    CONF_SOC_SENSOR:                     "_state_of_charge",
    CONF_PV_POWER_SENSOR:                "_solar_production",
    CONF_ADDITIONAL_GENERATION_SENSOR:   "_additional_production",
    CONF_HOUSE_POWER_SENSOR:             "_house_consumption",
    CONF_GRID_POWER_SENSOR:              "_transfer_to_from_grid",
    CONF_BATTERY_POWER_SENSOR:           "_battery_net_change",
    CONF_BATTERY_CHARGED_TODAY_SENSOR:   "_battery_charge_today",
    CONF_BATTERY_DISCHARGED_TODAY_SENSOR:"_battery_discharge_today",
    # Wallbox-Verbrauchszähler (E3DC RSCP, sumiert über alle Wallboxen)
    CONF_WALLBOX_POWER_SENSOR:           "_wallbox_consumption",
}


_OPENWB_CP_RE = re.compile(r"openwb_chargepoint_?(\d+)_")

# Domain der inoffiziellen evcc-HA-Integration (marq24/ha-evcc).
_EVCC_INTG_DOMAIN = "evcc_intg"


def _autodetect_evcc(hass) -> dict[str, Any]:
    """Detect entities provided by the marq24/ha-evcc integration.

    Looks up entities registered under the ``evcc_intg`` config entry and
    matches per-loadpoint suffixes:
    - ``binary_sensor.*_charging`` → ``evcc_charging_entity``
    - ``select.*_mode``            → ``evcc_mode_entity``

    The evcc loadpoint mode select uses ``"now"`` for instant charging,
    which matches the existing ``DEFAULT_EVCC_NOW_VALUE``. If multiple
    loadpoints exist, the alphabetically first match wins (deterministic).

    Returns an empty dict if no evcc integration is configured.
    """
    entries = hass.config_entries.async_entries(_EVCC_INTG_DOMAIN)
    if not entries:
        return {}
    entry_ids = {e.entry_id for e in entries}
    registry = er.async_get(hass)
    charging_candidates: list[str] = []
    mode_candidates: list[str] = []
    for ent in registry.entities.values():
        if ent.config_entry_id not in entry_ids:
            continue
        eid = ent.entity_id
        if eid.startswith("binary_sensor.") and eid.endswith("_charging"):
            charging_candidates.append(eid)
        elif eid.startswith("select.") and eid.endswith("_mode"):
            mode_candidates.append(eid)
    out: dict[str, Any] = {}
    if charging_candidates:
        out[CONF_EVCC_CHARGING_ENTITY] = sorted(charging_candidates)[0]
    if mode_candidates:
        out[CONF_EVCC_MODE_ENTITY] = sorted(mode_candidates)[0]
    if out:
        out[CONF_EVCC_ENABLED] = True
        out[CONF_EVCC_NOW_VALUE] = DEFAULT_EVCC_NOW_VALUE  # "now"
    return out


def _autodetect_openwb_wallbox(hass) -> str | None:
    """Find an openWB chargepoint power sensor.

    openWB exposes per-chargepoint power as ``sensor.openwb_chargepoint_<N>_ladeleistung``
    where ``<N>`` varies by installation. We pick the first match from the entity
    registry. If multiple chargepoints exist, the lowest-numbered one wins.
    """
    registry = er.async_get(hass)
    candidates: list[tuple[int, str]] = []
    for ent in registry.entities.values():
        eid = ent.entity_id
        if not eid.startswith("sensor.openwb_chargepoint"):
            continue
        if not eid.endswith("_ladeleistung"):
            continue
        m = _OPENWB_CP_RE.search(eid)
        if not m:
            continue
        candidates.append((int(m.group(1)), eid))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _autodetect_rscp_sources(hass) -> dict[str, Any]:
    """Resolve default sensor entity_ids from the e3dc_rscp integration via suffix matching.

    Also detects openWB chargepoint sensors as a fallback wallbox source when no
    E3DC wallbox sensor is present.
    """
    out: dict[str, Any] = {}
    rscp_entries = hass.config_entries.async_entries(E3DC_RSCP_DOMAIN)
    if rscp_entries:
        entry_ids = {e.entry_id for e in rscp_entries}
        registry = er.async_get(hass)
        rscp_sensor_ids = [
            ent.entity_id
            for ent in registry.entities.values()
            if ent.config_entry_id in entry_ids and ent.entity_id.startswith("sensor.")
        ]
        for key, suffix in _RSCP_SUFFIX_MAP.items():
            match = next((eid for eid in rscp_sensor_ids if eid.endswith(suffix)), None)
            if match:
                out[key] = match
    # _transfer_to_from_grid liefert positiv = Bezug → Vorzeichen automatisch invertieren.
    grid = out.get(CONF_GRID_POWER_SENSOR, "")
    if isinstance(grid, str) and grid.endswith("_transfer_to_from_grid"):
        out[CONF_GRID_POWER_INVERT] = True
    # Wallbox automatisch konfigurieren, wenn der RSCP-Sensor existiert.
    # E3DC-Wallbox hat einen eigenen Powermeter → NICHT im Hausverbrauch enthalten.
    if out.get(CONF_WALLBOX_POWER_SENSOR):
        out.setdefault(CONF_WALLBOX_PROVIDER, WALLBOX_PROVIDER_E3DC)
        out.setdefault(CONF_WALLBOX_TYPE, WALLBOX_TYPE_E3DC)
        out.setdefault(CONF_WALLBOX_INCLUDED_IN_HOUSE, False)
    else:
        # Fallback: openWB-Chargepoint suchen. Pattern: sensor.openwb_chargepoint*ladeleistung
        openwb = _autodetect_openwb_wallbox(hass)
        if openwb:
            out[CONF_WALLBOX_POWER_SENSOR] = openwb
            out[CONF_WALLBOX_PROVIDER] = WALLBOX_PROVIDER_OPENWB
            # openWB ist keine E3DC-Wallbox → Steuerlogik = generic.
            out[CONF_WALLBOX_TYPE] = WALLBOX_TYPE_GENERIC
            # openWB misst typischerweise nur den Chargepoint; der Hauszähler steht
            # am EVU und enthält die Wallbox-Leistung bereits → True als Default.
            out[CONF_WALLBOX_INCLUDED_IN_HOUSE] = True
    # EVCC-Integration (marq24/ha-evcc) ist orthogonal zur Wallbox-Quelle
    # → unabhängig erkennen und mit auffüllen.
    out.update(_autodetect_evcc(hass))
    return out


# Mapping CONF_KEY → (RSCP-Suffix, multiplier).
# multiplier=1000 für kW→W-Konversion, =1 wenn die Einheit bereits passt.
_RSCP_SYSTEM_PARAM_MAP: dict[str, tuple[str, float]] = {
    CONF_INSTALLED_KWP:          ("_installed_peak_power", 1.0),       # kW → kW
    CONF_INVERTER_POWER:         ("_maximum_ac_power", 1000.0),        # kW → W
    CONF_MAX_CHARGE_POWER:       ("_system_maximum_charge", 1000.0),   # kW → W
    CONF_FEED_IN_LIMIT_PERCENT:  ("_derate_feed_above", 1.0),          # % → %
    CONF_BATTERY_CAPACITY_KWH:   ("_installed_battery_capacity", 1.0), # kWh → kWh
}

# Anzeige-Labels und Einheiten für Auto-Detect-Übersicht.
_RSCP_SYSTEM_PARAM_LABELS: dict[str, tuple[str, str]] = {
    CONF_INSTALLED_KWP:          ("PV-Leistung",      "kWp"),
    CONF_INVERTER_POWER:         ("WR-Nennleistung",  "W"),
    CONF_MAX_CHARGE_POWER:       ("Max. Ladeleistung","W"),
    CONF_FEED_IN_LIMIT_PERCENT:  ("Einspeisegrenze",  "%"),
    CONF_BATTERY_CAPACITY_KWH:   ("Batteriekapazität","kWh"),
}


def _autodetect_rscp_system_params(hass) -> dict[str, Any]:
    """Read numeric system parameters (Wechselrichter, Batterie, Einspeisegrenze) from RSCP states."""
    rscp_entries = hass.config_entries.async_entries(E3DC_RSCP_DOMAIN)
    if not rscp_entries:
        return {}
    entry_ids = {e.entry_id for e in rscp_entries}
    registry = er.async_get(hass)
    rscp_sensor_ids = [
        ent.entity_id
        for ent in registry.entities.values()
        if ent.config_entry_id in entry_ids and ent.entity_id.startswith("sensor.")
    ]
    out: dict[str, Any] = {}
    for key, (suffix, mult) in _RSCP_SYSTEM_PARAM_MAP.items():
        eid = next((s for s in rscp_sensor_ids if s.endswith(suffix)), None)
        if not eid:
            continue
        state = hass.states.get(eid)
        if state is None or state.state in (None, "", "unknown", "unavailable"):
            continue
        try:
            raw = float(state.state)
        except (TypeError, ValueError):
            continue
        # Prefer the sensor's unit_of_measurement when present.
        # RSCP integration values have historically been inconsistent across
        # firmware/integration versions (kW vs W). The config flow wants:
        #  - inverter/max_charge_power in W
        #  - installed_kwp in kWp
        #  - battery_capacity_kwh in kWh
        #  - feed_in_limit_percent in %
        unit = (state.attributes.get("unit_of_measurement") or "").strip().lower()
        if key in (CONF_INVERTER_POWER, CONF_MAX_CHARGE_POWER):
            if unit in ("kw", "kilowatt"):
                mult_eff = 1000.0
            elif unit in ("w", "watt", "watts"):
                mult_eff = 1.0
            else:
                mult_eff = mult
            value = raw * mult_eff
        elif key == CONF_INSTALLED_KWP:
            # Target: kWp. If the sensor reports W, convert to kW.
            if unit in ("w", "watt", "watts"):
                value = raw / 1000.0
            else:
                value = raw * mult
        else:
            value = raw * mult
        # Prozent runden, sonst auf 1 Nachkommastelle für kWh / saubere Watt-Werte
        if key == CONF_FEED_IN_LIMIT_PERCENT:
            out[key] = round(value)
        elif mult == 1000.0:
            out[key] = round(value)
        else:
            out[key] = round(value, 2)
    return out


def _format_system_detection(detected: dict[str, Any]) -> str:
    """Render detected system params as a markdown bullet list for description placeholder."""
    if not detected:
        return "_(keine Werte aus RSCP-Diagnose verfügbar)_"
    lines = []
    for key, (label, unit) in _RSCP_SYSTEM_PARAM_LABELS.items():
        if key in detected:
            suffix = " _(Brutto – bitte unten Netto/nutzbar eintragen)_" if key == CONF_BATTERY_CAPACITY_KWH else ""
            lines.append(f"- {label}: **{detected[key]} {unit}**{suffix}")
    return "\n".join(lines) if lines else "_(keine Werte aus RSCP-Diagnose verfügbar)_"


def _format_sources_detection(detected: dict[str, Any]) -> str:
    """Render detected source sensors as a markdown bullet list."""
    if not detected:
        return "_(keine RSCP-Sensoren erkannt)_"
    # Nur Sensor-IDs (entity_id-Strings) auflisten; Bool-/Provider-Flags separat ausweisen.
    skip_keys = {
        CONF_GRID_POWER_INVERT,
        CONF_WALLBOX_PROVIDER,
        CONF_WALLBOX_INCLUDED_IN_HOUSE,
        CONF_EVCC_ENABLED,
        CONF_EVCC_NOW_VALUE,
    }
    sensor_lines = [
        f"- `{eid}`"
        for k, eid in detected.items()
        if k not in skip_keys
    ]
    if detected.get(CONF_GRID_POWER_INVERT):
        sensor_lines.append("- _Vorzeichen Netzleistung invertiert (positiv = Bezug)_")
    if detected.get(CONF_WALLBOX_PROVIDER):
        sensor_lines.append(
            f"- _Wallbox-Provider erkannt: **{detected[CONF_WALLBOX_PROVIDER]}**_"
        )
    if detected.get(CONF_EVCC_ENABLED):
        sensor_lines.append(
            f"- _EVCC-Integration erkannt (Sofortlade-Wert: `{detected.get(CONF_EVCC_NOW_VALUE, '')}`)_"
        )
    return "\n".join(sensor_lines)


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
        vol.Optional(CONF_GRID_POWER_INVERT, default=False): selector.BooleanSelector(),
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
        vol.Required(CONF_BATTERY_CAPACITY_KWH, default=DEFAULT_BATTERY_CAPACITY_KWH): _number_selector(1, 100, 0.5, "kWh"),
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
        vol.Optional(CONF_ADAPTIVE_RESERVE_MAX_SOC, default=DEFAULT_ADAPTIVE_RESERVE_MAX_SOC): _number_selector(5, 90, 1, "%"),
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
        vol.Required(CONF_TARIFF_MODE, default=DEFAULT_TARIFF_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=TARIFF_MODES,
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="tariff_mode",
            )
        ),
        vol.Optional(CONF_FIXED_BUY_PRICE, default=DEFAULT_FIXED_BUY_PRICE): _number_selector(0.0, 1.0, 0.001, "€/kWh"),
        vol.Optional(CONF_FEED_IN_PRICE, default=DEFAULT_FEED_IN_PRICE): _number_selector(0.0, 1.0, 0.001, "€/kWh"),
        vol.Optional(CONF_BATTERY_CAPEX_EUR, default=DEFAULT_BATTERY_CAPEX_EUR): _number_selector(0, 50000, 100, "€"),
        vol.Optional(CONF_BATTERY_TOTAL_CYCLES, default=DEFAULT_BATTERY_TOTAL_CYCLES): _number_selector(500, 20000, 100, "Zyklen"),
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
        # Separater Wallbox-Verbrauchszähler (entkoppelt EV-Last vom Hausverbrauch).
        # Funktioniert unabhängig von WALLBOX_ENABLED – auch wer keine Steuerung
        # über Maestro macht, kann hier seinen openWB/E3DC-Powermeter einbinden,
        # damit Optimizer/Forecast/EWMA nicht durch Ladespitzen verfälscht werden.
        vol.Optional(CONF_WALLBOX_POWER_SENSOR): _entity_selector(),
        vol.Optional(
            CONF_WALLBOX_INCLUDED_IN_HOUSE,
            default=DEFAULT_WALLBOX_INCLUDED_IN_HOUSE,
        ): selector.BooleanSelector(),
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
        # PV-Forecast-Sensoren (heute → morgen → übermorgen)
        vol.Optional(CONF_PV_FORECAST_SENSOR): _entity_selector(),
        vol.Optional(CONF_TOMORROW_PV_SENSOR): _entity_selector(),
        vol.Optional(CONF_PV_FORECAST_SENSOR_DAY2): _entity_selector(),
        # Schwellwerte / Akku-Parameter
        vol.Optional(
            CONF_PV_FORECAST_THRESHOLD_KWH, default=DEFAULT_PV_FORECAST_THRESHOLD_KWH
        ): _number_selector(0, 100, 0.5, "kWh"),
        vol.Optional(
            CONF_PV_FORECAST_SAFETY_FACTOR, default=DEFAULT_PV_FORECAST_SAFETY_FACTOR
        ): _number_selector(1.0, 3.0, 0.05),
        vol.Optional(
            CONF_DELAY_MIN_SOC, default=DEFAULT_DELAY_MIN_SOC
        ): _number_selector(0, 80, 5, "%"),
        # Spreading (Default: ON – Hardware-Schutz vor 0/8 kW-Bursts)
        vol.Optional(CONF_SPREADING_ENABLED, default=True): selector.BooleanSelector(),
        vol.Optional(
            CONF_SPREADING_TARGET_SOC, default=DEFAULT_SPREADING_TARGET_SOC
        ): _number_selector(50, 100, 1, "%"),
        # F1+: Forward-Looking (vorausschauende Ladung — nutzt den Morgen-Sensor oben)
        vol.Optional(
            CONF_FORWARD_LOOKING_ENABLED, default=DEFAULT_FORWARD_LOOKING_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_FORWARD_LOOKING_MAX_SOC, default=DEFAULT_FORWARD_LOOKING_MAX_SOC
        ): _number_selector(60, 100, 1, "%"),
        # Schwacher-PV-Tag: Akku-Priorität an bewölkten Tagen
        vol.Optional(
            CONF_LOW_YIELD_PRIORITY_ENABLED,
            default=DEFAULT_LOW_YIELD_PRIORITY_ENABLED,
        ): selector.BooleanSelector(),
        vol.Optional(CONF_PV_FORECAST_TODAY_SENSOR): _entity_selector(),
        vol.Optional(
            CONF_LOW_YIELD_THRESHOLD, default=DEFAULT_LOW_YIELD_THRESHOLD
        ): _number_selector(0.1, 1.0, 0.05),
        vol.Optional(
            CONF_LOW_YIELD_REFERENCE_KWH,
            default=DEFAULT_LOW_YIELD_REFERENCE_KWH,
        ): _number_selector(0, 500, 1, "kWh"),
        vol.Optional(
            CONF_LOW_YIELD_REFERENCE_KWH_PER_KWP,
            default=DEFAULT_LOW_YIELD_REFERENCE_KWH_PER_KWP,
        ): _number_selector(1.0, 10.0, 0.1, "kWh/kWp"),
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


async def _autodetect_sizing_sensors(hass) -> dict[str, Any]:
    """Auto-detect energy sensors for the sizing advisor.

    Primary source: HA Energy Dashboard (``async_get_manager``).  All sensors
    registered there have long-term statistics and are guaranteed to work with
    ``statistics_during_period``.
    Fallback: RSCP integration sensors matched by entity-id suffix.
    """
    out: dict[str, Any] = {}

    # ── 1. Try HA Energy Dashboard ────────────────────────────────────────────
    try:
        from homeassistant.components.energy import data as _energy_data  # noqa: PLC0415

        mgr = await _energy_data.async_get_manager(hass)
        prefs = (mgr.data or {}) if mgr.data else {}
        pv_sensors: list[str] = []
        for source in prefs.get("energy_sources", []):
            src_type = source.get("type")
            if src_type == "solar":
                stat = source.get("stat_energy_from")
                if stat:
                    pv_sensors.append(stat)
            elif src_type == "grid":
                for flow in source.get("flow_from", []):
                    stat = flow.get("stat_energy_from")
                    if stat and CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR not in out:
                        out[CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR] = stat
                for flow in source.get("flow_to", []):
                    stat = flow.get("stat_energy_to")
                    if stat and CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR not in out:
                        out[CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR] = stat
                # Also handle flat grid sources (stat_energy_from / stat_energy_to at top level)
                if CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR not in out:
                    stat = source.get("stat_energy_from")
                    if stat:
                        out[CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR] = stat
                if CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR not in out:
                    stat = source.get("stat_energy_to")
                    if stat:
                        out[CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR] = stat
            elif src_type == "battery":
                stat = source.get("stat_energy_to")
                if stat:
                    out[CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR] = stat
                stat = source.get("stat_energy_from")
                if stat:
                    out[CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR] = stat

        # Use all discovered PV sensors; user can deselect in the form
        if pv_sensors:
            out[CONF_SIZING_PV_ENERGY_SENSOR] = pv_sensors

        if out:
            # Energy Dashboard lookup succeeded – return immediately
            return out
    except Exception:  # noqa: BLE001
        pass

    # ── 2. Fallback: RSCP integration entity-id suffix matching ───────────────
    _RSCP_ENERGY_SUFFIX_MAP: dict[str, str] = {
        CONF_SIZING_PV_ENERGY_SENSOR:                "_solar_energy_produced",
        CONF_SIZING_HOUSE_ENERGY_SENSOR:             "_house_energy_consumed",
        CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR:       "_grid_in_energy",
        CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR:       "_grid_out_energy",
        CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR:    "_battery_energy_charged",
        CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR: "_battery_energy_discharged",
    }
    rscp_entries = hass.config_entries.async_entries(E3DC_RSCP_DOMAIN)
    if rscp_entries:
        entry_ids = {e.entry_id for e in rscp_entries}
        registry = er.async_get(hass)
        sensor_ids = [
            ent.entity_id
            for ent in registry.entities.values()
            if ent.config_entry_id in entry_ids and ent.entity_id.startswith("sensor.")
        ]
        for key, suffix in _RSCP_ENERGY_SUFFIX_MAP.items():
            match = next((eid for eid in sensor_ids if eid.endswith(suffix)), None)
            if match:
                out[key] = match
    return out


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

    VERSION = 3
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
        detected = _autodetect_rscp_sources(self.hass)
        suggested = {**detected, **self._data}
        schema = self.add_suggested_values_to_schema(STEP_SOURCES_SCHEMA, suggested)
        return self.async_show_form(
            step_id="sources",
            data_schema=schema,
            description_placeholders={
                "detected_count": str(len([k for k in detected if k != CONF_GRID_POWER_INVERT])),
                "detected_list": _format_sources_detection(detected),
            },
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 2: System parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_season()
        auto = _autodetect_rscp_system_params(self.hass)
        # Batteriekapazität ist BRUTTO – nicht als Vorschlag ins Feld schreiben,
        # User soll Netto/nutzbare Kapazität eintragen. Wert bleibt in der Übersicht sichtbar.
        auto_for_fields = {k: v for k, v in auto.items() if k != CONF_BATTERY_CAPACITY_KWH}
        suggested = {**auto_for_fields, **self._data}
        schema = self.add_suggested_values_to_schema(STEP_SYSTEM_SCHEMA, suggested)
        return self.async_show_form(
            step_id="system",
            data_schema=schema,
            description_placeholders={
                "detected_count": str(len(auto)),
                "detected_list": _format_system_detection(auto),
            },
        )

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
        # Auto-Detect Wallbox-Felder als Default-Vorschläge mitführen.
        auto = _autodetect_rscp_sources(self.hass)
        wb_keys = {
            CONF_WALLBOX_TYPE,
            CONF_WALLBOX_PROVIDER,
            CONF_WALLBOX_POWER_SENSOR,
            CONF_WALLBOX_INCLUDED_IN_HOUSE,
        }
        suggested = {k: v for k, v in auto.items() if k in wb_keys}
        suggested.update({k: v for k, v in self._data.items() if k in wb_keys})
        schema = self.add_suggested_values_to_schema(STEP_WALLBOX_SCHEMA, suggested)
        return self.async_show_form(step_id="wallbox", data_schema=schema)

    async def async_step_evcc(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 6b: EVCC integration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_heatpump()
        # Auto-Detect der evcc_intg-Integration (marq24/ha-evcc).
        auto = _autodetect_evcc(self.hass)
        suggested = {**auto, **self._data}
        schema = self.add_suggested_values_to_schema(STEP_EVCC_SCHEMA, suggested)
        return self.async_show_form(step_id="evcc", data_schema=schema)

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
            return await self.async_step_sizing_advisor()
        return self.async_show_form(step_id="auto_mode", data_schema=STEP_AUTO_MODE_SCHEMA)

    async def async_step_sizing_advisor(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Step 11: Battery & PV Sizing Advisor."""
        if user_input is not None:
            # Volatile toggle: re-import sensors from Energy Dashboard
            if user_input.pop(CONF_SIZING_IMPORT_FROM_ENERGY_DASHBOARD, False):
                detected = await _autodetect_sizing_sensors(self.hass)
                for k in (
                    CONF_SIZING_PV_ENERGY_SENSOR,
                    CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
                    CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
                    CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
                    CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
                ):
                    if k in detected:
                        user_input[k] = detected[k]
            # Strip empty entity selectors
            for k in (
                CONF_SIZING_PV_ENERGY_SENSOR,
                CONF_SIZING_HOUSE_ENERGY_SENSOR,
                CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
                CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
                CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
                CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
                CONF_SIZING_WALLBOX_ENERGY_SENSOR,
                CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR,
            ):
                if not user_input.get(k):
                    user_input.pop(k, None)
            self._data.update(user_input)
            return self.async_create_entry(title="E3DC Maestro", data={}, options=self._data)
        detected = await _autodetect_sizing_sensors(self.hass)
        # Normalize legacy string PV value to list (schema now uses multiple=True)
        cur = dict(self._data)
        pv_cur = cur.get(CONF_SIZING_PV_ENERGY_SENSOR)
        if isinstance(pv_cur, str):
            cur[CONF_SIZING_PV_ENERGY_SENSOR] = [pv_cur] if pv_cur else []
        # Detection wins only when the user has nothing saved yet for that key
        suggested = {**cur}
        for k, v in detected.items():
            if not suggested.get(k):
                suggested[k] = v
        schema = self.add_suggested_values_to_schema(STEP_SIZING_ADVISOR_SCHEMA, suggested)
        return self.async_show_form(step_id="sizing_advisor", data_schema=schema)

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
        return await self.async_step_init()

    def _prefilled(self, schema: vol.Schema) -> vol.Schema:
        """Return schema with current option values as defaults."""
        return self.add_suggested_values_to_schema(schema, self._options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # Load current options on first call (self.config_entry available from HA 2023.9+)
        if not self._options:
            self._options = dict(self.config_entry.options)
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "sources",
                "system",
                "season",
                "pv_forecast",
                "ht",
                "tariff_slots",
                "tariff",
                "wallbox",
                "evcc",
                "heatpump",
                "failsafe",
                "flat_curve",
                "auto_mode",
                "sizing_advisor",
                "finish",
            ],
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Save and close the options flow."""
        return self.async_create_entry(title="", data=self._options)

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        auto = _autodetect_rscp_sources(self.hass)
        # Für die Anzeige IMMER alle erkannten Werte zeigen, auch wenn nicht übernommen.
        detected_for_display = dict(auto)
        # Wenn grid_power_sensor bereits manuell konfiguriert ist, das invert-Flag
        # aus dem Auto-Detect NICHT übernehmen – sonst würden alte User mit
        # export_to_grid fälschlicherweise invert=True bekommen.
        if CONF_GRID_POWER_SENSOR in self._options:
            auto.pop(CONF_GRID_POWER_INVERT, None)
        suggested = {**auto, **self._options}
        schema = self.add_suggested_values_to_schema(STEP_SOURCES_SCHEMA, suggested)
        return self.async_show_form(
            step_id="sources",
            data_schema=schema,
            description_placeholders={
                "detected_count": str(len([k for k in detected_for_display if k != CONF_GRID_POWER_INVERT])),
                "detected_list": _format_sources_detection(detected_for_display),
            },
        )

    async def async_step_system(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        # Bestehende Options haben Vorrang; Auto-Detect füllt nur fehlende Felder.
        auto = _autodetect_rscp_system_params(self.hass)
        # Batteriekapazität ist BRUTTO – nicht als Vorschlag ins Feld schreiben.
        auto_for_fields = {k: v for k, v in auto.items() if k != CONF_BATTERY_CAPACITY_KWH}
        suggested = {**auto_for_fields, **self._options}
        schema = self.add_suggested_values_to_schema(STEP_SYSTEM_SCHEMA, suggested)
        return self.async_show_form(
            step_id="system",
            data_schema=schema,
            description_placeholders={
                "detected_count": str(len(auto)),
                "detected_list": _format_system_detection(auto),
            },
        )

    async def async_step_season(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="season", data_schema=self._prefilled(STEP_SEASON_SCHEMA))

    async def async_step_pv_forecast(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="pv_forecast", data_schema=self._prefilled(STEP_PV_FORECAST_SCHEMA))

    async def async_step_ht(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="ht", data_schema=self._prefilled(STEP_HT_SCHEMA))

    async def async_step_tariff(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="tariff", data_schema=self._prefilled(STEP_TARIFF_SCHEMA))

    async def async_step_wallbox(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        auto = _autodetect_rscp_sources(self.hass)
        wb_keys = {
            CONF_WALLBOX_TYPE,
            CONF_WALLBOX_PROVIDER,
            CONF_WALLBOX_POWER_SENSOR,
            CONF_WALLBOX_INCLUDED_IN_HOUSE,
        }
        suggested = {k: v for k, v in auto.items() if k in wb_keys}
        # Bestehende Optionen überschreiben Auto-Detect.
        suggested.update({k: v for k, v in self._options.items() if k in wb_keys})
        schema = self.add_suggested_values_to_schema(STEP_WALLBOX_SCHEMA, suggested)
        return self.async_show_form(step_id="wallbox", data_schema=schema)

    async def async_step_evcc(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        auto = _autodetect_evcc(self.hass)
        suggested = {**auto, **self._options}
        schema = self.add_suggested_values_to_schema(STEP_EVCC_SCHEMA, suggested)
        return self.async_show_form(step_id="evcc", data_schema=schema)

    async def async_step_heatpump(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="heatpump", data_schema=self._prefilled(STEP_HP_SCHEMA))

    async def async_step_failsafe(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="failsafe", data_schema=self._prefilled(STEP_FAILSAFE_SCHEMA))

    async def async_step_flat_curve(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="flat_curve", data_schema=self._prefilled(STEP_FLAT_CURVE_SCHEMA))

    async def async_step_auto_mode(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()
        return self.async_show_form(step_id="auto_mode", data_schema=self._prefilled(STEP_AUTO_MODE_SCHEMA))

    async def async_step_sizing_advisor(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            # Volatile toggle: re-import sensors from Energy Dashboard
            if user_input.pop(CONF_SIZING_IMPORT_FROM_ENERGY_DASHBOARD, False):
                detected = await _autodetect_sizing_sensors(self.hass)
                for k in (
                    CONF_SIZING_PV_ENERGY_SENSOR,
                    CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
                    CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
                    CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
                    CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
                ):
                    if k in detected:
                        user_input[k] = detected[k]
            for k in (
                CONF_SIZING_PV_ENERGY_SENSOR,
                CONF_SIZING_HOUSE_ENERGY_SENSOR,
                CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
                CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
                CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
                CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
                CONF_SIZING_WALLBOX_ENERGY_SENSOR,
                CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR,
            ):
                if not user_input.get(k):
                    user_input.pop(k, None)
            self._options.update(user_input)
            return await self.async_step_init()
        detected = await _autodetect_sizing_sensors(self.hass)
        cur = dict(self._options)
        pv_cur = cur.get(CONF_SIZING_PV_ENERGY_SENSOR)
        if isinstance(pv_cur, str):
            cur[CONF_SIZING_PV_ENERGY_SENSOR] = [pv_cur] if pv_cur else []
        suggested = {**cur}
        for k, v in detected.items():
            if not suggested.get(k):
                suggested[k] = v
        schema = self.add_suggested_values_to_schema(STEP_SIZING_ADVISOR_SCHEMA, suggested)
        return self.async_show_form(step_id="sizing_advisor", data_schema=schema)
