"""Sensor platform for E3DC Maestro."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALL_PHASES, DOMAIN
from .coordinator import E3DCMaestroCoordinator
from .explanation import decision_explanation as _decision_explanation


@dataclass(frozen=True, kw_only=True)
class MaestroSensorDescription(SensorEntityDescription):
    value_fn: Any = None


SENSOR_DESCRIPTIONS: tuple[MaestroSensorDescription, ...] = (
    MaestroSensorDescription(
        key="phase",
        name="Regelphase",
        icon="mdi:state-machine",
        device_class=SensorDeviceClass.ENUM,
        options=ALL_PHASES,
        value_fn=lambda coord: coord.last_decision.phase if coord.last_decision else None,
    ),
    MaestroSensorDescription(
        key="target_charge_power",
        name="Ziel-Ladeleistung",
        icon="mdi:battery-charging",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (coord.last_decision.target_charge_power or 0) if coord.last_decision else 0,
    ),
    MaestroSensorDescription(
        key="current_soc",
        name="Aktueller SoC",
        icon="mdi:battery",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(coord.data["state"].soc, 1)
            if coord.data and "state" in coord.data
            else None
        ),
    ),
    MaestroSensorDescription(
        key="target_soc",
        name="Ziel-SoC",
        icon="mdi:battery-clock",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: round(coord.last_decision.target_soc, 1) if coord.last_decision and coord.last_decision.target_soc is not None else None,
    ),
    MaestroSensorDescription(
        key="last_action",
        name="Letzte Aktion",
        icon="mdi:history",
        value_fn=lambda coord: coord.last_action_info.get("phase"),
    ),
    MaestroSensorDescription(
        key="decision_explanation",
        name="Entscheidungserklärung",
        icon="mdi:comment-question-outline",
        value_fn=lambda coord: _decision_explanation(coord),
    ),
    MaestroSensorDescription(
        key="charged_today",
        name="Geladen heute",
        icon="mdi:battery-plus",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("charged_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="discharged_today",
        name="Entladen heute",
        icon="mdi:battery-minus",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("discharged_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="feed_in_interventions",
        name="Einspeise-Eingriffe heute",
        icon="mdi:transmission-tower-export",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: coord.stats.get("feed_in_interventions_today", 0),
    ),
    MaestroSensorDescription(
        key="feed_in_avoided_today",
        name="DC-Abregelung verhindert heute",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("curtailment_avoided_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="pv_saved_today",
        name="PV-Verlust verhindert heute",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("pv_saved_today_kwh", 0), 3),
    ),
    # v0.2.0: Cost tracking
    MaestroSensorDescription(
        key="grid_draw_today",
        name="Netzbezug heute",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("grid_draw_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="grid_feed_in_today",
        name="Netzeinspeisung heute",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("grid_feed_in_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="kosten_heute",
        name="Stromkosten heute",
        icon="mdi:cash-minus",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("cost_today_eur", 0), 2),
    ),
    MaestroSensorDescription(
        key="einspeise_erloes_heute",
        name="Einspeise-Erlös heute",
        icon="mdi:cash-plus",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("feed_in_revenue_today_eur", 0), 2),
    ),
    MaestroSensorDescription(
        key="netto_kosten_heute",
        name="Netto-Stromkosten heute",
        icon="mdi:cash-sync",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda coord: round(
            coord.stats.get("cost_today_eur", 0)
            - coord.stats.get("feed_in_revenue_today_eur", 0),
            2,
        ),
    ),
    # v0.3.0: Eigenverbrauch, Ersparnis, Verschleiß, Bilanz
    MaestroSensorDescription(
        key="eigenverbrauch_heute",
        name="PV-Eigenverbrauch heute",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("pv_self_consumption_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="pv_ersparnis_heute",
        name="PV-Ersparnis heute",
        icon="mdi:piggy-bank-outline",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("pv_savings_today_eur", 0), 2),
    ),
    MaestroSensorDescription(
        key="akku_verschleiss_heute",
        name="Akku-Verschleiß heute",
        icon="mdi:battery-minus-variant",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("battery_wear_today_eur", 0), 3),
    ),
    MaestroSensorDescription(
        key="bilanz_heute",
        name="Energiebilanz heute",
        icon="mdi:scale-balance",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda coord: round(
            coord.stats.get("feed_in_revenue_today_eur", 0)
            + coord.stats.get("pv_savings_today_eur", 0)
            - coord.stats.get("cost_today_eur", 0)
            - coord.stats.get("battery_wear_today_eur", 0),
            2,
        ),
    ),
    MaestroSensorDescription(
        key="grid_to_battery_today",
        name="Netz → Akku heute",
        icon="mdi:battery-alert-variant-outline",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("grid_to_battery_today_kwh", 0), 3),
    ),
    MaestroSensorDescription(
        key="debug_log",
        name="Debug-Log",
        icon="mdi:text-box-outline",
        value_fn=lambda coord: "\n".join(list(coord.debug_log)[-5:]) if coord.debug_log else "",
    ),
    # C1: Autonomy time
    MaestroSensorDescription(
        key="autonomy_time",
        name="Autonomiezeit",
        icon="mdi:timer-outline",
        value_fn=lambda coord: coord.autonomy_str,
    ),
    # B1: Seasonal reserve SoC
    MaestroSensorDescription(
        key="seasonal_reserve_soc",
        name="Notstromreserve (aktuell)",
        icon="mdi:battery-alert",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: coord.seasonal_reserve_soc,
    ),
    # Phase D: adaptive emergency reserve SoC
    MaestroSensorDescription(
        key="adaptive_reserve_soc",
        name="Notstromreserve (adaptiv)",
        icon="mdi:battery-charging-medium",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: coord.adaptive_reserve_soc,
    ),
    # Phase D: adaptive HT reserve SoC
    MaestroSensorDescription(
        key="adaptive_ht_reserve_soc",
        name="HT-Reserve (adaptiv)",
        icon="mdi:battery-charging-medium",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: coord.adaptive_ht_reserve_soc,
    ),
    # F1+: Forward-Looking diagnostics
    MaestroSensorDescription(
        key="forward_looking_target_soc",
        name="Vorausschauendes Ladeziel",
        icon="mdi:battery-charging-high",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: coord.forward_looking_target_soc,
    ),
    MaestroSensorDescription(
        key="tomorrow_pv_kwh",
        name="Morgen PV-Prognose",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda coord: coord.tomorrow_pv_kwh,
    ),
    MaestroSensorDescription(
        key="tomorrow_deficit_kwh",
        name="Morgen Energiedefizit",
        icon="mdi:weather-cloudy-alert",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda coord: coord.tomorrow_deficit_kwh,
    ),
    # Schwacher-PV-Tag: Tagesprognose + Referenz + Verhältnis
    MaestroSensorDescription(
        key="low_yield_today_kwh",
        name="PV-Tagesprognose",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda coord: coord.low_yield_today_kwh,
    ),
    MaestroSensorDescription(
        key="low_yield_reference_kwh",
        name="PV-Referenz-Ertrag",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda coord: coord.low_yield_reference_kwh,
    ),
    MaestroSensorDescription(
        key="low_yield_ratio",
        name="PV-Tag Quote",
        icon="mdi:percent-outline",
        value_fn=lambda coord: coord.low_yield_ratio,
    ),
    # E3/Phase 1: Curtailment avoided today (Diagnose; kombiniert in pv_saved_today)
    MaestroSensorDescription(
        key="curtailment_avoided_today",
        name="Abregelung verhindert heute",
        icon="mdi:shield-sun",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("feed_in_avoided_today_kwh", 0), 3),
    ),
    # Phase 5: Seasonal charge-end hour
    MaestroSensorDescription(
        key="seasonal_charge_end",
        name="Saisonales Ladeende (Uhrzeit)",
        icon="mdi:clock-end",
        value_fn=lambda coord: coord.seasonal_charge_end_str,
    ),
    # Phase 7: Astro charge-start (sunrise + offset)
    MaestroSensorDescription(
        key="astro_charge_start",
        name="Astro-Ladestart (Uhrzeit)",
        icon="mdi:clock-start",
        value_fn=lambda coord: coord.astro_charge_start_str,
    ),
    # Prognose: Ladeende und Ladestart morgen
    MaestroSensorDescription(
        key="tomorrow_charge_end",
        name="Ladeende morgen (Prognose)",
        icon="mdi:clock-end",
        value_fn=lambda coord: coord.tomorrow_charge_end_str,
    ),
    MaestroSensorDescription(
        key="tomorrow_charge_start",
        name="Ladestart morgen (Prognose)",
        icon="mdi:clock-start",
        value_fn=lambda coord: coord.tomorrow_charge_start_str,
    ),
    # PV-Verzögerung: voraussichtlicher Ladestart heute
    MaestroSensorDescription(
        key="pv_delay_charge_start",
        name="Verzögerter Ladestart heute",
        icon="mdi:clock-alert-outline",
        value_fn=lambda coord: coord.pv_delay_charge_start_str,
    ),
    # F1: 24h Forecast sensors (enabled by default; return unknown until ≥7d history available)
    MaestroSensorDescription(
        key="forecast_min_soc",
        name="Forecast: Min-SoC nächste 24h",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement="%",
        value_fn=lambda coord: coord.forecast.min_soc if coord.forecast else None,
    ),
    MaestroSensorDescription(
        key="forecast_max_soc",
        name="Forecast: Max-SoC nächste 24h",
        icon="mdi:battery-arrow-up-outline",
        native_unit_of_measurement="%",
        value_fn=lambda coord: coord.forecast.max_soc if coord.forecast else None,
    ),
    MaestroSensorDescription(
        key="forecast_grid_draw_kwh",
        name="Forecast: Netzbezug nächste 24h",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda coord: coord.forecast.grid_draw_kwh if coord.forecast else None,
    ),
    MaestroSensorDescription(
        key="forecast_self_sufficiency",
        name="Forecast: Autarkie nächste 24h",
        icon="mdi:solar-panel",
        native_unit_of_measurement="%",
        value_fn=lambda coord: (
            round(coord.forecast.self_sufficiency * 100, 1)
            if coord.forecast and coord.forecast.self_sufficiency is not None
            else None
        ),
    ),
    # F2: Trajectory sensor (attributes used by ApexCharts)
    MaestroSensorDescription(
        key="forecast_trajectory",
        name="Forecast: SoC-Trajektorie 24h",
        icon="mdi:chart-line",
        native_unit_of_measurement="%",
        value_fn=lambda coord: coord.forecast.min_soc if coord.forecast else None,
    ),
    # F2: Diagnose-Sensor für Forecast-Datenqualität
    MaestroSensorDescription(
        key="forecast_data_quality",
        name="Forecast: Datenqualit\u00e4t",
        icon="mdi:database-check",
        value_fn=lambda coord: _forecast_quality_state(coord),
    ),
    # F3: Auto-Optimierungs-Modus
    MaestroSensorDescription(
        key="auto_active_strategy",
        name="Auto: Aktive Strategie",
        icon="mdi:auto-fix",
        value_fn=lambda coord: _auto_active_strategy_state(coord),
    ),
    MaestroSensorDescription(
        key="auto_estimated_savings",
        name="Auto: Geschätzte Einsparung",
        icon="mdi:piggy-bank",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(coord._auto_result.estimated_savings_eur, 3)
            if getattr(coord, "_auto_result", None) is not None
            and not coord._auto_result.fallback
            else None
        ),
    ),
    MaestroSensorDescription(
        key="charge_power_limit",
        name="Aktives Lade-Limit",
        icon="mdi:battery-lock",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            int(coord.last_decision.charge_power_limit)
            if coord.last_decision and coord.last_decision.charge_power_limit is not None
            else None
        ),
    ),
    MaestroSensorDescription(
        key="discharge_power_limit",
        name="Aktives Entlade-Limit",
        icon="mdi:battery-off-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            int(coord.last_decision.discharge_power_limit)
            if coord.last_decision and coord.last_decision.discharge_power_limit is not None
            else None
        ),
    ),
    # Wallbox / Verbrauchsaufteilung
    MaestroSensorDescription(
        key="wallbox_power",
        name="Wallbox-Leistung",
        icon="mdi:ev-station",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(coord.data["state"].wallbox_power, 1)
            if coord.data and coord.data.get("state") is not None
            else None
        ),
    ),
    MaestroSensorDescription(
        key="total_load_power",
        name="Gesamtlast (Haus + Wallbox)",
        icon="mdi:home-lightning-bolt",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(
                (coord.data["state"].house_power or 0.0)
                + (coord.data["state"].wallbox_power or 0.0),
                1,
            )
            if coord.data and coord.data.get("state") is not None
            else None
        ),
    ),
    MaestroSensorDescription(
        key="wallbox_energy_today",
        name="Wallbox-Energie heute",
        icon="mdi:ev-station",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coord: round(coord.stats.get("wallbox_energy_today_kwh", 0.0), 3),
    ),
    # ── Battery & PV Sizing Advisor – read-only KPI sensors ─────────────────
    # (Interpolated from the 2D matrix based on the two slider values)
    MaestroSensorDescription(
        key="sizing_status",
        name="Advisor: Status",
        icon="mdi:chart-timeline-variant-shimmer",
        value_fn=lambda coord: (
            "running" if coord.sizing_running
            else ("ready" if coord.sizing_analysis else "not_run")
        ),
    ),
    MaestroSensorDescription(
        key="sizing_self_sufficiency",
        name="Advisor: Autarkie (Szenario)",
        icon="mdi:solar-panel",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            None
            if _sizing_interpolate(coord) is None
            or math.isnan(_sizing_interpolate(coord).self_sufficiency_pct)
            else _sizing_interpolate(coord).self_sufficiency_pct
        ),
    ),
    MaestroSensorDescription(
        key="sizing_avoided_import_kwh",
        name="Advisor: Vermiedener Netzbezug/Jahr",
        icon="mdi:transmission-tower-off",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            _sizing_interpolate(coord).avoided_grid_import_kwh
            if _sizing_interpolate(coord) is not None else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_savings_eur_per_year",
        name="Advisor: Ersparnis/Jahr",
        icon="mdi:piggy-bank-outline",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda coord: (
            _sizing_interpolate(coord).savings_eur_per_year
            if _sizing_interpolate(coord) is not None else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_investment_eur",
        name="Advisor: Investition",
        icon="mdi:cash-multiple",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=lambda coord: _sizing_live_investment(coord),
    ),
    MaestroSensorDescription(
        key="sizing_payback_years",
        name="Advisor: Amortisationszeit",
        icon="mdi:calendar-clock",
        native_unit_of_measurement="a",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: _sizing_live_payback(coord),
    ),
    MaestroSensorDescription(
        key="sizing_cycles_per_year",
        name="Advisor: Zyklen/Jahr (virt. Akku)",
        icon="mdi:battery-sync-outline",
        native_unit_of_measurement="1/a",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            _sizing_interpolate(coord).cycles_per_year
            if _sizing_interpolate(coord) is not None else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_baseline_grid_import_kwh",
        name="Advisor: Netzbezug Baseline/Jahr",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(sum(coord.sizing_analysis.baseline.monthly_baseline_grid_in), 1)
            if coord.sizing_analysis else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_economic_payback",
        name="Advisor: Wirtschaftl. Empfehlung Amortisation",
        icon="mdi:cash-clock",
        native_unit_of_measurement="a",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            coord.sizing_analysis.recommended_economic.payback_years
            if coord.sizing_analysis and coord.sizing_analysis.recommended_economic
            else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_technical_autarky",
        name="Advisor: Techn. Empfehlung Autarkie",
        icon="mdi:battery-high",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            coord.sizing_analysis.recommended_technical.self_sufficiency_pct
            if coord.sizing_analysis and coord.sizing_analysis.recommended_technical
            else None
        ),
    ),
    MaestroSensorDescription(
        key="sizing_anomaly_rate",
        name="Advisor: Energiebilanz-Anomalierate",
        icon="mdi:alert-outline",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coord: (
            round(coord.sizing_analysis.anomaly_rate * 100, 1)
            if coord.sizing_analysis else None
        ),
    ),
)


def _auto_active_strategy_state(coord) -> str:
    if not getattr(coord, "_params", None) or not coord._params.auto_mode_enabled:
        return "manuell"
    res = getattr(coord, "_auto_result", None)
    if res is None:
        # Auto an, aber Optimizer noch nie gelaufen
        return "auto: pending"
    if res.fallback:
        # Echter Fallback – zu wenig Daten
        return "auto: Daten-Fallback"
    if not res.overrides:
        # Optimizer lief, aber Baseline war bereits optimal
        return "auto: Baseline optimal"
    return "auto: aktiv"


def _forecast_quality_state(coord) -> str:
    cs = getattr(coord, "_consumption_stats", None)
    pv = getattr(coord, "_pv_stats", None)
    cons_ok = cs is not None and any(v > 0 for v in cs.hourly_profile_w)
    pv_ok = pv is not None and any(v > 0 for v in pv.hourly_profile_w)
    if cons_ok and pv_ok:
        return "ok"
    if cons_ok and not pv_ok:
        return "pv_fallback"
    if pv_ok and not cons_ok:
        return "consumption_fallback"
    return "both_fallback"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        MaestroSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    # Sizing Advisor – dedicated subclasses:
    #  • MaestroSizingSensor       → heavy, static analysis result (matrix, recommendations).
    #    Only re-writes state when the analysis itself changes.
    #  • MaestroSizingScenarioSensor → lightweight, slider-dependent scenario KPIs.
    #    Re-writes on every slider change but stays well below the 16 KB attribute limit.
    entities.append(MaestroSizingSensor(coordinator))
    entities.append(MaestroSizingScenarioSensor(coordinator))
    async_add_entities(entities)


class MaestroSensor(CoordinatorEntity[E3DCMaestroCoordinator], SensorEntity):
    entity_description: MaestroSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: E3DCMaestroCoordinator, description: MaestroSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        key = self.entity_description.key
        if key == "last_action":
            return self.coordinator.last_action_info
        if key == "decision_explanation":
            coord = self.coordinator
            dec = coord.last_decision
            if dec is None:
                return None
            return {
                "phase": dec.phase,
                "reason": dec.reason,
                "target_soc": dec.target_soc,
                "target_charge_power": dec.target_charge_power,
                "charge_power_limit": dec.charge_power_limit,
                "discharge_power_limit": dec.discharge_power_limit,
                "feed_in_excess_w": dec.feed_in_excess_w,
                "timestamp": coord.last_action_info.get("timestamp"),
            }
        if key == "autonomy_time":
            coord = self.coordinator
            window = coord._house_power_window
            interval_s = coord.update_interval.total_seconds()
            current = (
                abs(coord.data["state"].house_power)
                if coord.data and "state" in coord.data
                else None
            )
            return {
                "median_house_power_w": round(coord.avg_house_power_w, 1),
                "current_house_power_w": round(current, 1) if current is not None else None,
                "window_minutes": round(len(window) * interval_s / 60, 1),
                "samples": len(window),
                "samples_required": coord._AUTONOMY_MIN_SAMPLES,
            }
        if key == "seasonal_reserve_soc":
            p = self.coordinator._params
            return {
                "enabled": p.seasonal_reserve_enabled,
                "winter_percent": p.reserve_winter_percent,
                "equinox_percent": p.reserve_equinox_percent,
            }
        if key in ("adaptive_reserve_soc", "adaptive_ht_reserve_soc"):
            p = self.coordinator._params
            stats = self.coordinator._consumption_stats
            return {
                "enabled": p.adaptive_reserve_enabled,
                "lookback_days": p.adaptive_reserve_lookback_days,
                "min_days_required": p.adaptive_reserve_min_days,
                "data_days": stats.data_days if stats else 0,
                "avg_w_24h": round(stats.avg_w_24h, 1) if stats and stats.avg_w_24h is not None else None,
                "avg_w_ht_window": round(stats.avg_w_ht_window, 1) if stats and stats.avg_w_ht_window is not None else None,
                "safety_factor": p.adaptive_reserve_safety_factor,
            }
        if key == "forecast_trajectory":
            fc = self.coordinator.forecast
            if fc is None:
                return {"trajectory_points": [], "trajectory_soc": [], "trajectory_phases": []}
            # Pre-compute [timestamp_ms, soc] pairs so data_generator needs no JS date math.
            # v0.3.0: trajectory has 96 quarter-hour entries (15-min spacing) instead of 24.
            # Backward-compat: handle both lengths gracefully via len-based step calc.
            now_utc = datetime.now(timezone.utc)
            n = len(fc.trajectory_soc)
            # 24h total span → step_ms = 24h / n
            step_ms = (24 * 3_600_000) // max(n, 1)
            # Round base to the same grid the simulator used (15-min for n=96, 1h otherwise)
            if n >= 96:
                base = now_utc.replace(second=0, microsecond=0)
                base = base.replace(minute=(base.minute // 15) * 15)
            else:
                base = now_utc.replace(minute=0, second=0, microsecond=0)
            base_ms = int(base.timestamp() * 1000)
            points = [
                [base_ms + (i + 1) * step_ms, v]
                for i, v in enumerate(fc.trajectory_soc)
            ]
            return {
                "trajectory_points": points,
                "trajectory_soc": fc.trajectory_soc,
                "trajectory_phases": fc.trajectory_phases,
                "min_soc": fc.min_soc,
                "max_soc": fc.max_soc,
                "grid_draw_kwh": fc.grid_draw_kwh,
                "grid_feed_in_kwh": fc.grid_feed_in_kwh,
                "self_sufficiency_pct": (
                    round(fc.self_sufficiency * 100, 1) if fc.self_sufficiency is not None else None
                ),
            }
        if key == "forecast_data_quality":
            cs = getattr(self.coordinator, "_consumption_stats", None)
            pv = getattr(self.coordinator, "_pv_stats", None)
            cons_profile = cs.hourly_profile_w if cs else [0.0] * 24
            pv_profile = pv.hourly_profile_w if pv else [0.0] * 24
            return {
                "consumption_sensor_configured": cs is not None,
                "consumption_data_days": cs.data_days if cs else 0,
                "consumption_profile_max_w": round(max(cons_profile), 1) if cons_profile else 0,
                "consumption_profile_avg_w": round(sum(cons_profile) / 24, 1) if cons_profile else 0,
                "consumption_profile_nonzero_hours": sum(1 for v in cons_profile if v > 0),
                "pv_sensor_configured": pv is not None,
                "pv_data_days": pv.data_days if pv else 0,
                "pv_profile_max_w": round(max(pv_profile), 1) if pv_profile else 0,
                "pv_profile_avg_w": round(sum(pv_profile) / 24, 1) if pv_profile else 0,
                "pv_profile_nonzero_hours": sum(1 for v in pv_profile if v > 0),
                "hint": (
                    "PV-Profil leer – Solcast/Forecast.Solar-Sensor empfehlenswert"
                    if not pv_profile or max(pv_profile) == 0
                    else None
                ),
            }
        if key == "auto_active_strategy":
            res = getattr(self.coordinator, "_auto_result", None)
            last_run = getattr(self.coordinator, "_auto_last_run", None)
            fc = res.forecast if res else None
            base = res.baseline_forecast if res else None
            params = self.coordinator._params
            buy = getattr(params, "fixed_buy_price", 0.30)
            sell = getattr(params, "feed_in_price", 0.08)

            def _delta(a, b, ndigits=2):
                if a is None or b is None:
                    return None
                return round(a - b, ndigits)

            attrs = {
                "auto_mode_enabled": params.auto_mode_enabled,
                "objective": params.auto_mode_objective,
                "last_run": last_run.isoformat() if last_run else None,
                "fallback": res.fallback if res else None,
                "fallback_reason": res.fallback_reason if res else None,
                "overrides": res.overrides if res else {},
                "grid_size": res.grid_size if res else 0,
                "horizon_h": (
                    48 if (fc and len(fc.trajectory_soc) > 96) else
                    24 if fc else None
                ),
                "estimated_savings_pct": res.estimated_savings_pct if res and not res.fallback else None,
                "estimated_savings_eur": res.estimated_savings_eur if res and not res.fallback else None,
                "tariff_buy_price_eur_kwh": round(buy, 4),
                "tariff_feed_in_price_eur_kwh": round(sell, 4),
                # Simulated forecast (24h baseline-or-best result)
                "sim_self_sufficiency": round(fc.self_sufficiency, 3) if fc and fc.self_sufficiency is not None else None,
                "sim_curtailed_kwh": round(fc.pv_curtailed_kwh, 2) if fc else None,
                "sim_grid_feed_in_kwh": round(fc.grid_feed_in_kwh, 2) if fc else None,
                "sim_grid_draw_kwh": round(fc.grid_draw_kwh, 2) if fc else None,
                "sim_min_soc": round(fc.min_soc, 1) if fc else None,
                "sim_max_soc": round(fc.max_soc, 1) if fc else None,
                # Baseline (= ohne Auto-Override)
                "baseline_self_sufficiency": round(base.self_sufficiency, 3) if base and base.self_sufficiency is not None else None,
                "baseline_curtailed_kwh": round(base.pv_curtailed_kwh, 2) if base else None,
                "baseline_grid_feed_in_kwh": round(base.grid_feed_in_kwh, 2) if base else None,
                "baseline_grid_draw_kwh": round(base.grid_draw_kwh, 2) if base else None,
                "baseline_min_soc": round(base.min_soc, 1) if base else None,
                # Live-Deltas (best − baseline) → was hat die Optimierung bewirkt?
                "delta_grid_draw_kwh": _delta(fc.grid_draw_kwh, base.grid_draw_kwh) if fc and base else None,
                "delta_grid_feed_in_kwh": _delta(fc.grid_feed_in_kwh, base.grid_feed_in_kwh) if fc and base else None,
                "delta_curtailed_kwh": _delta(fc.pv_curtailed_kwh, base.pv_curtailed_kwh) if fc and base else None,
                "delta_self_sufficiency": _delta(fc.self_sufficiency, base.self_sufficiency, ndigits=3) if fc and base else None,
                "delta_min_soc": _delta(fc.min_soc, base.min_soc, ndigits=1) if fc and base else None,
                # €-Aufschlüsselung der Einsparung (Forecast-basiert)
                "savings_from_less_grid_draw_eur": round((base.grid_draw_kwh - fc.grid_draw_kwh) * buy, 3) if fc and base else None,
                "savings_from_more_feed_in_eur": round((fc.grid_feed_in_kwh - base.grid_feed_in_kwh) * sell, 3) if fc and base else None,
            }
            return attrs
        return None


def _sizing_interpolate(coord: "E3DCMaestroCoordinator"):
    """Return a bilinear-interpolated ScenarioResult for the current slider values."""
    if coord.sizing_analysis is None:
        return None
    from .battery_sizing import interpolate_result
    return interpolate_result(
        coord.sizing_analysis,
        coord.sizing_hypothetical_kwh,
        coord.sizing_hypothetical_pv_kwp,
    )


def _sizing_live_investment(coord: "E3DCMaestroCoordinator") -> float | None:
    """Compute investment € live from dashboard-editable price fields.

    Decoupled from the baked-in sweep prices so the user can adjust costs
    without re-running the full analysis.
    """
    interp = _sizing_interpolate(coord)
    if interp is None:
        return None
    battery_kwh = float(coord.sizing_hypothetical_kwh or 0.0)
    pv_kwp = float(coord.sizing_hypothetical_pv_kwp or 0.0)
    wr_upgrade = bool(interp.inverter_upgrade_needed)
    investment = (
        battery_kwh * float(coord.sizing_price_battery_kwh)
        + pv_kwp * float(coord.sizing_price_pv_kwp)
        + (float(coord.sizing_price_inverter) if wr_upgrade else 0.0)
        + float(coord.sizing_price_extra)
    )
    return round(investment, 0)


def _sizing_live_payback(coord: "E3DCMaestroCoordinator") -> float | None:
    """Compute payback years from live investment / interpolated savings."""
    interp = _sizing_interpolate(coord)
    if interp is None:
        return None
    inv = _sizing_live_investment(coord)
    if inv is None:
        return None
    savings = interp.savings_eur_per_year or 0.0
    if savings <= 1e-6:
        return None
    return round(inv / savings, 1)


class MaestroSizingSensor(CoordinatorEntity["E3DCMaestroCoordinator"], SensorEntity):
    """Heavy aggregating sensor exposing the static sizing analysis result.

    Holds the full 2D matrix and the recommendation dicts. To keep WebSocket
    chatter and recorder load low, state is only re-written when the underlying
    analysis (``coordinator.sizing_analysis.computed_at``) actually changes or
    the running flag toggles. Slider movements do **not** trigger updates here;
    those flow through :class:`MaestroSizingScenarioSensor` instead.
    """

    _attr_has_entity_name = True
    _attr_name = "Advisor: Sizing-Matrix"
    _attr_icon = "mdi:grid"
    _attr_unique_id_suffix = "sizing_matrix"

    def __init__(self, coordinator: "E3DCMaestroCoordinator") -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_sizing_matrix"
        self._attr_device_info = _device_info(coordinator)
        self._last_computed_at: Any = None
        self._last_running: bool | None = None

    def _handle_coordinator_update(self) -> None:
        """Suppress redundant writes when nothing relevant changed."""
        coord = self.coordinator
        sa = coord.sizing_analysis
        computed_at = sa.computed_at if sa else None
        running = bool(coord.sizing_running)
        if computed_at == self._last_computed_at and running == self._last_running:
            return
        self._last_computed_at = computed_at
        self._last_running = running
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> str | None:
        if self.coordinator.sizing_analysis is None:
            return "not_run"
        sa = self.coordinator.sizing_analysis
        return sa.computed_at.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        coord = self.coordinator
        sa = coord.sizing_analysis
        if sa is None:
            return {
                "status": "running" if coord.sizing_running else "not_run",
            }

        import math

        def _dump_rec(r) -> dict | None:
            if r is None:
                return None
            return {
                "battery_kwh": r.battery_kwh,
                "pv_kwp": r.pv_kwp,
                "strategy": r.strategy,
                "payback_years": (
                    None if r.payback_years is None or r.payback_years == math.inf
                    else round(r.payback_years, 2)
                ),
                "self_sufficiency_pct": r.self_sufficiency_pct,
                "savings_eur_per_year": r.savings_eur_per_year,
                "investment_eur": r.investment_eur,
                "reason": r.reason,
            }

        # Pre-aggregate the two slices the dashboard actually charts so the
        # 16 KB attribute limit is never hit and the browser does not have to
        # filter/sort 143 dicts on every state push.
        autarky_by_battery_pv0: list[dict] = []
        for bi, b_kwh in enumerate(sa.battery_sizes_kwh):
            # Find the column with PV ≈ 0 kWp
            for pi, p_kwp in enumerate(sa.pv_sizes_kwp):
                if abs(p_kwp) < 1e-6:
                    r = sa.matrix[bi][pi]
                    autarky_by_battery_pv0.append({
                        "b": b_kwh,
                        "autarky": r.self_sufficiency_pct,
                    })
                    break

        scenarios_flat: list[dict] = []
        for bi, b_kwh in enumerate(sa.battery_sizes_kwh):
            for pi, p_kwp in enumerate(sa.pv_sizes_kwp):
                r = sa.matrix[bi][pi]
                if r.savings_eur_per_year <= 0:
                    continue
                scenarios_flat.append({
                    "b": b_kwh,
                    "p": p_kwp,
                    "savings": round(r.savings_eur_per_year, 1),
                    "invest": round(r.investment_eur, 1),
                })
        top_savings_scenarios = sorted(
            scenarios_flat, key=lambda x: -x["savings"]
        )[:10]

        return {
            "status": "running" if coord.sizing_running else "ready",
            "records_count": sa.records_count,
            "analysis_days": sa.analysis_days,
            "anomaly_rate_pct": round(sa.anomaly_rate * 100, 1),
            "computed_at": sa.computed_at.isoformat(),
            "autarky_by_battery_pv0": autarky_by_battery_pv0,
            "top_savings_scenarios": top_savings_scenarios,
            "recommended_economic": _dump_rec(sa.recommended_economic),
            "recommended_technical": _dump_rec(sa.recommended_technical),
            "recommended_balanced": _dump_rec(sa.recommended_balanced),
            "baseline_grid_import_kwh": round(sum(sa.baseline.monthly_baseline_grid_in), 1),
            "baseline_self_sufficiency_pct": sa.baseline.self_sufficiency_pct,
        }


class MaestroSizingScenarioSensor(CoordinatorEntity["E3DCMaestroCoordinator"], SensorEntity):
    """Lightweight sensor for slider-dependent scenario KPIs.

    Re-renders on every coordinator update (incl. slider changes) but only
    carries a handful of small attributes – well below the recorder's 16 KB
    attribute limit and cheap to serialize over the WebSocket.
    """

    _attr_has_entity_name = True
    _attr_name = "Advisor: Szenario"
    _attr_icon = "mdi:tune-variant"
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator: "E3DCMaestroCoordinator") -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_sizing_scenario"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> float | None:
        interp = _sizing_interpolate(self.coordinator)
        if interp is None:
            return None
        import math
        v = interp.savings_eur_per_year
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
        return round(v, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        coord = self.coordinator
        if coord.sizing_analysis is None:
            return {
                "status": "running" if coord.sizing_running else "not_run",
                "slider_battery_kwh": coord.sizing_hypothetical_kwh,
                "slider_pv_kwp": coord.sizing_hypothetical_pv_kwp,
            }
        import math
        interp = _sizing_interpolate(coord)
        # Live-Investitionsberechnung: aus den (dashboard-editierbaren)
        # Preis-Eingaben + dem WR-Upgrade-Flag der interpolierten Zelle.
        battery_kwh = float(coord.sizing_hypothetical_kwh or 0.0)
        pv_kwp = float(coord.sizing_hypothetical_pv_kwp or 0.0)
        wr_upgrade = bool(interp.inverter_upgrade_needed) if interp else False
        investment_live = (
            battery_kwh * float(coord.sizing_price_battery_kwh)
            + pv_kwp * float(coord.sizing_price_pv_kwp)
            + (float(coord.sizing_price_inverter) if wr_upgrade else 0.0)
            + float(coord.sizing_price_extra)
        )
        savings = interp.savings_eur_per_year if interp else 0.0
        if savings and savings > 1e-6:
            payback_live = investment_live / savings
        else:
            payback_live = math.inf
        return {
            "status": "running" if coord.sizing_running else "ready",
            "slider_battery_kwh": battery_kwh,
            "slider_pv_kwp": pv_kwp,
            "scenario_self_sufficiency_pct": interp.self_sufficiency_pct if interp else None,
            "scenario_avoided_kwh": interp.avoided_grid_import_kwh if interp else None,
            "scenario_savings_eur": savings,
            "scenario_investment_eur": round(investment_live, 0),
            "scenario_investment_breakdown": {
                "battery_eur": round(battery_kwh * float(coord.sizing_price_battery_kwh), 0),
                "pv_eur": round(pv_kwp * float(coord.sizing_price_pv_kwp), 0),
                "inverter_eur": round(float(coord.sizing_price_inverter), 0) if wr_upgrade else 0,
                "extra_eur": round(float(coord.sizing_price_extra), 0),
                "inverter_upgrade_needed": wr_upgrade,
            },
            "scenario_payback_years": (
                None if payback_live == math.inf else round(payback_live, 1)
            ),
            "scenario_monthly_avoided_kwh": interp.monthly_avoided_kwh if interp else None,
            "scenario_monthly_baseline_grid_in": interp.monthly_baseline_grid_in if interp else None,
        }



def _device_info(coordinator: E3DCMaestroCoordinator) -> dict:
    return {
        "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
        "name": "E3DC Maestro",
        "manufacturer": "E3DC Maestro",
        "model": "Charge Orchestrator",
        "sw_version": "0.1.5",
    }
