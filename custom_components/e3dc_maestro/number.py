"""Number platform for E3DC Maestro – live parameter tuning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTime, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CHARGE_RAMP_W_PER_CYCLE,
    CONF_CHARGE_TARGET,
    CONF_CHARGE_TARGET_LATE,
    CONF_CHARGE_THRESHOLD,
    CONF_CHEAP_THRESHOLD,
    CONF_CURTAILMENT_ACTIVATION_W,
    CONF_CURTAILMENT_RELEASE_W,
    CONF_FEED_IN_LIMIT_PERCENT,
    CONF_HP_MAX_PRICE,
    CONF_HP_MIN_PAUSE_MINUTES,
    CONF_HP_MIN_RUN_MINUTES,
    CONF_HP_MIN_SURPLUS,
    CONF_HT_MIN,
    CONF_HT_OFF,
    CONF_HT_ON,
    CONF_HT_SOCKEL,
    CONF_INSTALLED_KWP,
    CONF_INVERTER_POWER,
    CONF_LATE_CHARGE_END_H,
    CONF_LOWER_CORRIDOR,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_GRID_CHARGE_KWH,
    CONF_MIN_CHARGE_POWER,
    CONF_RESERVE_EQUINOX_PERCENT,
    CONF_RESERVE_WINTER_PERCENT,
    CONF_SOC_HYSTERESIS_PERCENT,
    CONF_SUMMER_CHARGE_END,
    CONF_SUMMER_MAXIMUM_HOUR,
    CONF_UPDATE_INTERVAL,
    CONF_UPPER_CORRIDOR,
    CONF_WALLBOX_MAX_CURRENT,
    CONF_WALLBOX_MIN_CURRENT,
    CONF_WALLBOX_MIN_SURPLUS,
    CONF_WATCHDOG_TIMEOUT,
    CONF_WINTER_MINIMUM_HOUR,
    CONF_MORNING_UNLOAD_SOC,
    CONF_MORNING_UNLOAD_START_SOC,
    CONF_PRE_DISCHARGE_OFFSET_H,
    CONF_PRE_DISCHARGE_MAX_POWER_W,
    CONF_FORCE_DISCHARGE_POWER_W,
    CONF_MORNING_GRID_EXPORT_THRESHOLD,
    CONF_CHARGE_END_SUNSET_OFFSET_H,
    CONF_CHARGE_START_SUNRISE_OFFSET_H,
    CONF_SPREADING_TARGET_SOC,
    CONF_MORNING_CAP_SOC,
    CONF_MORNING_CAP_UNTIL_H,
    CONF_GENTLE_CHARGE_FACTOR,
    CONF_DELAY_MIN_SOC,
    CONF_HARD_SOC_LIMIT,
    CONF_FORWARD_LOOKING_MAX_SOC,
    CONF_EVCC_DISCHARGE_LIMIT_W,
    DOMAIN,
)
from .coordinator import E3DCMaestroCoordinator
from .sensor import _device_info


@dataclass(frozen=True, kw_only=True)
class MaestroNumberDescription(NumberEntityDescription):
    param_key: str = ""
    min_value: float = 0
    max_value: float = 100
    step_value: float = 1
    mode: NumberMode = NumberMode.BOX
    advanced: bool = False   # hidden unless advanced_corridor enabled


NUMBER_DESCRIPTIONS: tuple[MaestroNumberDescription, ...] = (
    # ── System ────────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_INVERTER_POWER,
        name="WR-Leistung",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_INVERTER_POWER,
        min_value=1000, max_value=30000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_MAX_CHARGE_POWER,
        name="Max. Ladeleistung",
        icon="mdi:battery-charging-high",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_MAX_CHARGE_POWER,
        min_value=500, max_value=15000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_MIN_CHARGE_POWER,
        name="Min. Ladeleistung",
        icon="mdi:battery-charging-low",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_MIN_CHARGE_POWER,
        min_value=50, max_value=5000, step_value=50,
    ),
    MaestroNumberDescription(
        key=CONF_INSTALLED_KWP,
        name="Installierte PV-Leistung",
        icon="mdi:solar-panel",
        native_unit_of_measurement="kWp",
        param_key=CONF_INSTALLED_KWP,
        min_value=0.5, max_value=100, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_FEED_IN_LIMIT_PERCENT,
        name="Einspeisegrenze",
        icon="mdi:transmission-tower",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_FEED_IN_LIMIT_PERCENT,
        min_value=0, max_value=100, step_value=1,
    ),
    # ── Season ────────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_CHARGE_THRESHOLD,
        name="Ladeschwelle",
        icon="mdi:battery-low",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_CHARGE_THRESHOLD,
        min_value=0, max_value=50, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_CHARGE_TARGET,
        name="Ladeende SoC",
        icon="mdi:battery-check",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_CHARGE_TARGET,
        min_value=50, max_value=100, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_WINTER_MINIMUM_HOUR,
        name="Ladeende Winter",
        icon="mdi:weather-snowy",
        native_unit_of_measurement="h",
        param_key=CONF_WINTER_MINIMUM_HOUR,
        min_value=6, max_value=18, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_SUMMER_MAXIMUM_HOUR,
        name="Ladeende Sommer",
        icon="mdi:weather-sunny",
        native_unit_of_measurement="h",
        param_key=CONF_SUMMER_MAXIMUM_HOUR,
        min_value=8, max_value=20, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_SUMMER_CHARGE_END,
        name="Sommerladeende Ziel",
        icon="mdi:sun-clock",
        native_unit_of_measurement="h",
        param_key=CONF_SUMMER_CHARGE_END,
        min_value=12, max_value=23, step_value=0.5,
    ),
    # ── E2: Spreading ────────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_SPREADING_TARGET_SOC,
        name="Spreading-Ziel SoC",
        icon="mdi:chart-timeline-variant",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_SPREADING_TARGET_SOC,
        min_value=50, max_value=100, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_LOWER_CORRIDOR,
        name="Unterer Ladekorridor",
        icon="mdi:arrow-down-bold",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_LOWER_CORRIDOR,
        min_value=0, max_value=5000, step_value=50,
        advanced=True,
    ),
    MaestroNumberDescription(
        key=CONF_UPPER_CORRIDOR,
        name="Oberer Ladekorridor",
        icon="mdi:arrow-up-bold",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_UPPER_CORRIDOR,
        min_value=0, max_value=15000, step_value=50,
        advanced=True,
    ),
    # ── HT ────────────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_HT_ON,
        name="HT Beginn",
        icon="mdi:clock-start",
        native_unit_of_measurement="h",
        param_key=CONF_HT_ON,
        min_value=0, max_value=23, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_HT_OFF,
        name="HT Ende",
        icon="mdi:clock-end",
        native_unit_of_measurement="h",
        param_key=CONF_HT_OFF,
        min_value=0, max_value=23, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_HT_MIN,
        name="HT-Reserve Winter",
        icon="mdi:battery-50",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_HT_MIN,
        min_value=0, max_value=100, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_HT_SOCKEL,
        name="HT-Sockel Äquinoktium",
        icon="mdi:battery-20",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_HT_SOCKEL,
        min_value=0, max_value=100, step_value=1,
    ),
    # ── Dynamic tariff ────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_CHEAP_THRESHOLD,
        name="Günstig-Schwelle",
        icon="mdi:currency-eur",
        native_unit_of_measurement="€/kWh",
        param_key=CONF_CHEAP_THRESHOLD,
        min_value=0, max_value=1.0, step_value=0.01,
    ),
    MaestroNumberDescription(
        key=CONF_MAX_GRID_CHARGE_KWH,
        name="Max. Netzladung/Tag",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement="kWh",
        param_key=CONF_MAX_GRID_CHARGE_KWH,
        min_value=0, max_value=20, step_value=0.5,
    ),
    # ── Wallbox ───────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_WALLBOX_MIN_CURRENT,
        name="Wallbox Min-Strom",
        icon="mdi:current-ac",
        native_unit_of_measurement="A",
        param_key=CONF_WALLBOX_MIN_CURRENT,
        min_value=6, max_value=32, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_WALLBOX_MAX_CURRENT,
        name="Wallbox Max-Strom",
        icon="mdi:current-ac",
        native_unit_of_measurement="A",
        param_key=CONF_WALLBOX_MAX_CURRENT,
        min_value=6, max_value=32, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_WALLBOX_MIN_SURPLUS,
        name="Wallbox Mindest-Überschuss",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_WALLBOX_MIN_SURPLUS,
        min_value=0, max_value=10000, step_value=100,
    ),
    # ── Heat pump ─────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_HP_MIN_SURPLUS,
        name="WP Mindest-Überschuss",
        icon="mdi:heat-pump-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_HP_MIN_SURPLUS,
        min_value=0, max_value=10000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_HP_MAX_PRICE,
        name="WP Max-Preis",
        icon="mdi:currency-eur",
        native_unit_of_measurement="€/kWh",
        param_key=CONF_HP_MAX_PRICE,
        min_value=0, max_value=1.0, step_value=0.01,
    ),
    MaestroNumberDescription(
        key=CONF_HP_MIN_RUN_MINUTES,
        name="WP Mindestlaufzeit",
        icon="mdi:timer-play",
        native_unit_of_measurement="min",
        param_key=CONF_HP_MIN_RUN_MINUTES,
        min_value=0, max_value=120, step_value=5,
    ),
    MaestroNumberDescription(
        key=CONF_HP_MIN_PAUSE_MINUTES,
        name="WP Mindestpause",
        icon="mdi:timer-pause",
        native_unit_of_measurement="min",
        param_key=CONF_HP_MIN_PAUSE_MINUTES,
        min_value=0, max_value=120, step_value=5,
    ),
    # ── Failsafe ──────────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_WATCHDOG_TIMEOUT,
        name="Watchdog-Timeout",
        icon="mdi:dog",
        native_unit_of_measurement="min",
        param_key=CONF_WATCHDOG_TIMEOUT,
        min_value=0, max_value=60, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_UPDATE_INTERVAL,
        name="Aktualisierungsintervall",
        icon="mdi:update",
        native_unit_of_measurement="s",
        param_key=CONF_UPDATE_INTERVAL,
        min_value=10, max_value=120, step_value=5,
    ),    # ── A1/A2: Hysterese + Ramp ─────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_SOC_HYSTERESIS_PERCENT,
        name="SoC-Hysterese",
        icon="mdi:arrow-collapse-horizontal",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_SOC_HYSTERESIS_PERCENT,
        min_value=0, max_value=10, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_CHARGE_RAMP_W_PER_CYCLE,
        name="Ladeleistungs-Anlauf",
        icon="mdi:speedometer-slow",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_CHARGE_RAMP_W_PER_CYCLE,
        min_value=0, max_value=2000, step_value=50,
    ),
    # ── B1: Saisonale Reserve ──────────────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_RESERVE_WINTER_PERCENT,
        name="Notstromreserve Winter",
        icon="mdi:snowflake-alert",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_RESERVE_WINTER_PERCENT,
        min_value=0, max_value=80, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_RESERVE_EQUINOX_PERCENT,
        name="Notstromreserve Äquinoktium",
        icon="mdi:battery-alert-variant-outline",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_RESERVE_EQUINOX_PERCENT,
        min_value=0, max_value=50, step_value=1,    ),
    # ── E3/Phase 1: Curtailment Guard ─────────────────────────────────
    MaestroNumberDescription(
        key=CONF_CURTAILMENT_ACTIVATION_W,
        name="Abregelschutz Einschaltschwelle",
        icon="mdi:shield-sun",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_CURTAILMENT_ACTIVATION_W,
        min_value=100, max_value=5000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_CURTAILMENT_RELEASE_W,
        name="Abregelschutz Ausschaltschwelle",
        icon="mdi:shield-sun-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_CURTAILMENT_RELEASE_W,
        min_value=0, max_value=2000, step_value=100,
    ),
    # ── Phase 4: Two-Tier Ladeende ────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_CHARGE_TARGET_LATE,
        name="Spätziel SoC",
        icon="mdi:battery-charging-high",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_CHARGE_TARGET_LATE,
        min_value=50, max_value=100, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_LATE_CHARGE_END_H,
        name="Spät-Ladeende (Stunde)",
        icon="mdi:clock-end",
        native_unit_of_measurement="h",
        param_key=CONF_LATE_CHARGE_END_H,
        min_value=14, max_value=23, step_value=0.5,
    ),
    # ── Phase 6: Morning Pre-Discharge ─────────────────────────────────
    MaestroNumberDescription(
        key=CONF_MORNING_UNLOAD_SOC,
        name="Vorentladungs-Ziel SoC",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_MORNING_UNLOAD_SOC,
        min_value=0, max_value=80, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_MORNING_UNLOAD_START_SOC,
        name="Vorentladungs-Einschwelle SoC",
        icon="mdi:battery-80",
        native_unit_of_measurement=PERCENTAGE,
        param_key=CONF_MORNING_UNLOAD_START_SOC,
        min_value=30, max_value=95, step_value=1,
    ),
    MaestroNumberDescription(
        key=CONF_PRE_DISCHARGE_OFFSET_H,
        name="Vorentladungs-Offset (Stunden vor Ladestart)",
        icon="mdi:clock-minus-outline",
        native_unit_of_measurement="h",
        param_key=CONF_PRE_DISCHARGE_OFFSET_H,
        min_value=0, max_value=8, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_PRE_DISCHARGE_MAX_POWER_W,
        name="Vorentladungs-Max. Leistung",
        icon="mdi:flash-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_PRE_DISCHARGE_MAX_POWER_W,
        min_value=100, max_value=5000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_FORCE_DISCHARGE_POWER_W,
        name="Erzwungene Entladungsleistung",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_FORCE_DISCHARGE_POWER_W,
        min_value=100, max_value=10000, step_value=100,
    ),
    MaestroNumberDescription(
        key=CONF_MORNING_GRID_EXPORT_THRESHOLD,
        name="Tibber-Schwelle für Netzexport",
        icon="mdi:currency-eur",
        native_unit_of_measurement="€/kWh",
        param_key=CONF_MORNING_GRID_EXPORT_THRESHOLD,
        min_value=0.05, max_value=0.50, step_value=0.01,
    ),
    # ── Phase 7: Astro-Modus ────────────────────────────────────────
    # Lat/Lon werden automatisch aus der HA-Konfiguration übernommen
    MaestroNumberDescription(
        key=CONF_CHARGE_END_SUNSET_OFFSET_H,
        name="Ladeende Offset zu Sonnenuntergang",
        icon="mdi:weather-sunset-down",
        native_unit_of_measurement="h",
        param_key=CONF_CHARGE_END_SUNSET_OFFSET_H,
        min_value=-8, max_value=2, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_CHARGE_START_SUNRISE_OFFSET_H,
        name="Ladestart Offset nach Sonnenaufgang",
        icon="mdi:weather-sunset-up",
        native_unit_of_measurement="h",
        param_key=CONF_CHARGE_START_SUNRISE_OFFSET_H,
        min_value=-2, max_value=8, step_value=0.5,
    ),
    # ── F0: Morning-Cap + Gentle-Charge ────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_MORNING_CAP_SOC,
        name="Morning-Cap SoC-Grenze",
        icon="mdi:battery-clock-outline",
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.BATTERY,
        param_key=CONF_MORNING_CAP_SOC,
        min_value=10, max_value=80, step_value=5,
    ),
    MaestroNumberDescription(
        key=CONF_DELAY_MIN_SOC,
        name="Mindest-SoC vor Verzögerung",
        icon="mdi:battery-arrow-up-outline",
        native_unit_of_measurement="%",
        device_class=NumberDeviceClass.BATTERY,
        param_key=CONF_DELAY_MIN_SOC,
        min_value=0, max_value=80, step_value=5,
    ),
    MaestroNumberDescription(
        key=CONF_MORNING_CAP_UNTIL_H,
        name="Morning-Cap aktiv bis (Uhr, lokal)",
        icon="mdi:clock-alert-outline",
        native_unit_of_measurement="h",
        param_key=CONF_MORNING_CAP_UNTIL_H,
        min_value=0, max_value=14, step_value=0.5,
    ),
    MaestroNumberDescription(
        key=CONF_GENTLE_CHARGE_FACTOR,
        name="Schonladung Faktor",
        icon="mdi:leaf-circle-outline",
        native_unit_of_measurement="",
        param_key=CONF_GENTLE_CHARGE_FACTOR,
        min_value=0.05, max_value=1.0, step_value=0.05,
    ),
    # ── G0: Hard SoC Limit ─────────────────────────────────────────────
    MaestroNumberDescription(
        key=CONF_HARD_SOC_LIMIT,
        name="Hard-SoC-Limit (Akku-Deckel)",
        icon="mdi:battery-lock",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        param_key=CONF_HARD_SOC_LIMIT,
        min_value=50, max_value=100, step_value=1,
    ),
    # ── F1+: Forward-Looking (vorausschauende Ladung) ───────────────────────
    MaestroNumberDescription(
        key=CONF_FORWARD_LOOKING_MAX_SOC,
        name="Vorausschauende Ladung Max-SoC",
        icon="mdi:weather-partly-cloudy",
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        param_key=CONF_FORWARD_LOOKING_MAX_SOC,
        min_value=60, max_value=100, step_value=1,
    ),
    # ── D1: EVCC Now-Modus Entladungslimit ─────────────────────────────────
    MaestroNumberDescription(
        key=CONF_EVCC_DISCHARGE_LIMIT_W,
        name="EVCC Now-Modus Entladungslimit",
        icon="mdi:car-electric",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        param_key=CONF_EVCC_DISCHARGE_LIMIT_W,
        min_value=0, max_value=15000, step_value=50,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MaestroNumber(coordinator, desc) for desc in NUMBER_DESCRIPTIONS
    )


class MaestroNumber(CoordinatorEntity[E3DCMaestroCoordinator], NumberEntity):
    entity_description: MaestroNumberDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: E3DCMaestroCoordinator, description: MaestroNumberDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator)
        self._attr_native_min_value = description.min_value
        self._attr_native_max_value = description.max_value
        self._attr_native_step = description.step_value
        self._attr_mode = description.mode

    @property
    def native_value(self) -> float | None:
        return getattr(self.coordinator._params, self.entity_description.param_key, None)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.update_param(self.entity_description.param_key, value)
        self.async_write_ha_state()
