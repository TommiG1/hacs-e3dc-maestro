"""Sensor platform for E3DC Maestro."""
from __future__ import annotations

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
        name="Einspeiselimit gesichert heute",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda coord: round(coord.stats.get("feed_in_avoided_today_kwh", 0), 3),
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
        entity_registry_enabled_default=False,
        value_fn=lambda coord: coord.seasonal_reserve_soc,
    ),
    # Phase D: adaptive emergency reserve SoC
    MaestroSensorDescription(
        key="adaptive_reserve_soc",
        name="Notstromreserve (adaptiv)",
        icon="mdi:battery-charging-medium",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda coord: coord.adaptive_reserve_soc,
    ),
    # Phase D: adaptive HT reserve SoC
    MaestroSensorDescription(
        key="adaptive_ht_reserve_soc",
        name="HT-Reserve (adaptiv)",
        icon="mdi:battery-charging-medium",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
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
    # E3/Phase 1: Curtailment avoided today (Diagnose; kombiniert in pv_saved_today)
    MaestroSensorDescription(
        key="curtailment_avoided_today",
        name="Abregelung verhindert heute",
        icon="mdi:shield-sun",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda coord: round(coord.stats.get("curtailment_avoided_today_kwh", 0), 3),
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
    # F1: 24h Forecast sensors (enabled by default; return unknown until ≥7d history available)
    MaestroSensorDescription(
        key="forecast_min_soc",
        name="Forecast: Min-SoC nächste 24h",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        value_fn=lambda coord: coord.forecast.min_soc if coord.forecast else None,
    ),
    MaestroSensorDescription(
        key="forecast_max_soc",
        name="Forecast: Max-SoC nächste 24h",
        icon="mdi:battery-arrow-up-outline",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
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
        native_unit_of_measurement="%",
        value_fn=lambda coord: (
            coord._auto_result.estimated_savings_pct
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
    async_add_entities(
        MaestroSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


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
            # Pre-compute [timestamp_ms, soc] pairs so data_generator needs no JS date math
            now_utc = datetime.now(timezone.utc)
            base = now_utc.replace(minute=0, second=0, microsecond=0)
            ms_per_hour = 3_600_000
            base_ms = int(base.timestamp() * 1000)
            points = [
                [base_ms + (i + 1) * ms_per_hour, v]
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
            return {
                "auto_mode_enabled": self.coordinator._params.auto_mode_enabled,
                "objective": self.coordinator._params.auto_mode_objective,
                "last_run": last_run.isoformat() if last_run else None,
                "fallback": res.fallback if res else None,
                "fallback_reason": res.fallback_reason if res else None,
                "overrides": res.overrides if res else {},
                "grid_size": res.grid_size if res else 0,
                "estimated_savings_pct": res.estimated_savings_pct if res and not res.fallback else None,
                # Simulated forecast (24h baseline-or-best result)
                "sim_self_sufficiency": round(fc.self_sufficiency, 3) if fc and fc.self_sufficiency is not None else None,
                "sim_curtailed_kwh": round(fc.pv_curtailed_kwh, 2) if fc else None,
                "sim_grid_feed_in_kwh": round(fc.grid_feed_in_kwh, 2) if fc else None,
                "sim_grid_draw_kwh": round(fc.grid_draw_kwh, 2) if fc else None,
                "sim_min_soc": round(fc.min_soc, 1) if fc else None,
                "sim_max_soc": round(fc.max_soc, 1) if fc else None,
            }
        return None


def _device_info(coordinator: E3DCMaestroCoordinator) -> dict:
    return {
        "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
        "name": "E3DC Maestro",
        "manufacturer": "E3DC Maestro",
        "model": "Charge Orchestrator",
        "sw_version": "0.1.5",
    }
