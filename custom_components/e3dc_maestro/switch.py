"""Switch platform for E3DC Maestro."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ADAPTIVE_RESERVE_ENABLED,
    CONF_ADVANCED_CORRIDOR,
    CONF_CURTAILMENT_GUARD_ENABLED,
    CONF_EVCC_ENABLED,
    CONF_FAST_CHARGE_FLOOR_ENABLED,
    CONF_HP_ENABLED,
    CONF_HT_ENABLED,
    CONF_HT_SAT,
    CONF_HT_SUN,
    CONF_LOWER_CORRIDOR_PAUSE_ENABLED,
    CONF_PRE_DISCHARGE_TIBBER_AUTO,
    CONF_SPREADING_ENABLED,
    CONF_ASTRO_ENABLED,
    CONF_MORNING_CAP_ENABLED,
    CONF_GENTLE_CHARGE_ENABLED,
    CONF_AUTO_MODE_ENABLED,
    CONF_HARD_SOC_LIMIT_ENABLED,
    CONF_FORWARD_LOOKING_ENABLED,
    CONF_LOW_YIELD_PRIORITY_ENABLED,
    CONF_PV_FORECAST_ENABLED,
    CONF_SEASONAL_RESERVE_ENABLED,
    CONF_TWO_TIER_ENABLED,
    CONF_WALLBOX_ENABLED,
    DOMAIN,
)
from .coordinator import E3DCMaestroCoordinator
from .sensor import _device_info


@dataclass(frozen=True, kw_only=True)
class MaestroSwitchDescription(SwitchEntityDescription):
    param_key: str | None = None      # coordinator param to read/write
    on_fn: Any = None                 # called on turn_on
    off_fn: Any = None                # called on turn_off


SWITCH_DESCRIPTIONS: tuple[MaestroSwitchDescription, ...] = (
    MaestroSwitchDescription(
        key="regelung_aktiv",
        name="Regelung aktiv",
        icon="mdi:tune",
        on_fn=lambda coord: coord.set_regelung_aktiv(True),
        off_fn=lambda coord: coord.set_regelung_aktiv(False),
    ),
    MaestroSwitchDescription(
        key="force_discharge",
        name="Erzwungene Entladung",
        icon="mdi:battery-arrow-down",
        on_fn=lambda coord: coord.set_force_discharge(True),
        off_fn=lambda coord: coord.set_force_discharge(False),
    ),
    MaestroSwitchDescription(
        key=CONF_HT_ENABLED,
        name="HT/NT-Schutz",
        icon="mdi:clock-alert",
        param_key=CONF_HT_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_HT_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_HT_ENABLED, False),
    ),
    MaestroSwitchDescription(
        key=CONF_HT_SAT,
        name="HT Samstag",
        icon="mdi:calendar-weekend",
        param_key=CONF_HT_SAT,
        on_fn=lambda coord: coord.update_param(CONF_HT_SAT, True),
        off_fn=lambda coord: coord.update_param(CONF_HT_SAT, False),
    ),
    MaestroSwitchDescription(
        key=CONF_HT_SUN,
        name="HT Sonntag",
        icon="mdi:calendar-weekend-outline",
        param_key=CONF_HT_SUN,
        on_fn=lambda coord: coord.update_param(CONF_HT_SUN, True),
        off_fn=lambda coord: coord.update_param(CONF_HT_SUN, False),
    ),
    MaestroSwitchDescription(
        key=CONF_WALLBOX_ENABLED,
        name="Wallbox-Regelung",
        icon="mdi:ev-station",
        param_key=CONF_WALLBOX_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_WALLBOX_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_WALLBOX_ENABLED, False),
    ),
    MaestroSwitchDescription(
        key=CONF_HP_ENABLED,
        name="Wärmepumpen-Regelung",
        icon="mdi:heat-pump",
        param_key=CONF_HP_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_HP_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_HP_ENABLED, False),
    ),
    MaestroSwitchDescription(
        key="debug",
        name="Debug-Logging",
        icon="mdi:bug",
        on_fn=lambda coord: setattr(coord, "debug_enabled", True),
        off_fn=lambda coord: setattr(coord, "debug_enabled", False),
    ),
    # B1: Saisonale Notstromreserve
    MaestroSwitchDescription(
        key=CONF_SEASONAL_RESERVE_ENABLED,
        name="Saisonale Notstromreserve",
        icon="mdi:battery-alert",
        param_key=CONF_SEASONAL_RESERVE_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_SEASONAL_RESERVE_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_SEASONAL_RESERVE_ENABLED, False),
    ),
    # Phase D: verbrauchsadaptive Reserve
    MaestroSwitchDescription(
        key=CONF_ADAPTIVE_RESERVE_ENABLED,
        name="Adaptive Reserve (Verbrauchsmittel)",
        icon="mdi:chart-line-variant",
        param_key=CONF_ADAPTIVE_RESERVE_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_ADAPTIVE_RESERVE_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_ADAPTIVE_RESERVE_ENABLED, False),
    ),
    # D1: EVCC-Integration
    MaestroSwitchDescription(
        key=CONF_EVCC_ENABLED,
        name="EVCC-Integration",
        icon="mdi:car-electric",
        param_key=CONF_EVCC_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_EVCC_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_EVCC_ENABLED, False),
    ),
    # E3/Phase 1: Curtailment Guard
    MaestroSwitchDescription(
        key=CONF_CURTAILMENT_GUARD_ENABLED,
        name="Abregelschutz",
        icon="mdi:shield-sun",
        param_key=CONF_CURTAILMENT_GUARD_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_CURTAILMENT_GUARD_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_CURTAILMENT_GUARD_ENABLED, False),
    ),
    # Phase 2: Untere-Korridor-Pause
    MaestroSwitchDescription(
        key=CONF_LOWER_CORRIDOR_PAUSE_ENABLED,
        name="Korridor-Pause (min. Ladeleistung)",
        icon="mdi:pause-circle-outline",
        param_key=CONF_LOWER_CORRIDOR_PAUSE_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_LOWER_CORRIDOR_PAUSE_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_LOWER_CORRIDOR_PAUSE_ENABLED, False),
    ),
    # Erweiterter Korridor: SoC-Delta → Leistung linear zw. unterem/oberem Korridor
    MaestroSwitchDescription(
        key=CONF_ADVANCED_CORRIDOR,
        name="Erweiterter Ladekorridor",
        icon="mdi:chart-sankey",
        param_key=CONF_ADVANCED_CORRIDOR,
        on_fn=lambda coord: coord.update_param(CONF_ADVANCED_CORRIDOR, True),
        off_fn=lambda coord: coord.update_param(CONF_ADVANCED_CORRIDOR, False),
    ),
    # Schnelllade-Boden: bis floor_soc ohne Korridor-Cap mit vollem PV-Überschuss
    MaestroSwitchDescription(
        key=CONF_FAST_CHARGE_FLOOR_ENABLED,
        name="Schnelllade-Boden",
        icon="mdi:battery-charging-50",
        param_key=CONF_FAST_CHARGE_FLOOR_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_FAST_CHARGE_FLOOR_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_FAST_CHARGE_FLOOR_ENABLED, False),
    ),
    # Phase 4: Two-Tier Ladeende
    MaestroSwitchDescription(
        key=CONF_TWO_TIER_ENABLED,
        name="Spät-Ladung (Two-Tier)",
        icon="mdi:battery-charging-high",
        param_key=CONF_TWO_TIER_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_TWO_TIER_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_TWO_TIER_ENABLED, False),
    ),
    # Phase 6: Morning Pre-Discharge – Tibber Auto
    MaestroSwitchDescription(
        key=CONF_PRE_DISCHARGE_TIBBER_AUTO,
        name="Vorentladung Tibber-Auto",
        icon="mdi:lightning-bolt-circle",
        param_key=CONF_PRE_DISCHARGE_TIBBER_AUTO,
        on_fn=lambda coord: coord.update_param(CONF_PRE_DISCHARGE_TIBBER_AUTO, True),
        off_fn=lambda coord: coord.update_param(CONF_PRE_DISCHARGE_TIBBER_AUTO, False),
    ),
    # E2: Ladeverteilung (Spreading)
    MaestroSwitchDescription(
        key=CONF_SPREADING_ENABLED,
        name="Ladeverteilung (Spreading)",
        icon="mdi:chart-bell-curve-cumulative",
        param_key=CONF_SPREADING_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_SPREADING_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_SPREADING_ENABLED, False),
    ),
    # Phase 7: Astro-Modus
    MaestroSwitchDescription(
        key=CONF_ASTRO_ENABLED,
        name="Astro-Modus (Sonnenüberwachung)",
        icon="mdi:white-balance-sunny",
        param_key=CONF_ASTRO_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_ASTRO_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_ASTRO_ENABLED, False),
    ),
    # F0: Morning-Cap + Gentle-Charge
    MaestroSwitchDescription(
        key=CONF_MORNING_CAP_ENABLED,
        name="Morning-Cap (SoC-Deckel morgens)",
        icon="mdi:battery-clock-outline",
        param_key=CONF_MORNING_CAP_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_MORNING_CAP_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_MORNING_CAP_ENABLED, False),
    ),
    MaestroSwitchDescription(
        key=CONF_GENTLE_CHARGE_ENABLED,
        name="Schonladung (reduzierte Ladeleistung)",
        icon="mdi:leaf-circle-outline",
        param_key=CONF_GENTLE_CHARGE_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_GENTLE_CHARGE_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_GENTLE_CHARGE_ENABLED, False),
    ),
    MaestroSwitchDescription(
        key=CONF_AUTO_MODE_ENABLED,
        name="Auto-Optimierung",
        icon="mdi:brain",
        param_key=CONF_AUTO_MODE_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_AUTO_MODE_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_AUTO_MODE_ENABLED, False),
    ),
    # G0: Hard SoC Limit (Akku-Schonung)
    MaestroSwitchDescription(
        key=CONF_HARD_SOC_LIMIT_ENABLED,
        name="Hard-SoC-Limit (Akku-Deckel)",
        icon="mdi:battery-lock",
        param_key=CONF_HARD_SOC_LIMIT_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_HARD_SOC_LIMIT_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_HARD_SOC_LIMIT_ENABLED, False),
    ),
    # F1+: Forward-Looking (vorausschauende Ladung)
    MaestroSwitchDescription(
        key=CONF_FORWARD_LOOKING_ENABLED,
        name="Vorausschauende Ladung",
        icon="mdi:weather-partly-cloudy",
        param_key=CONF_FORWARD_LOOKING_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_FORWARD_LOOKING_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_FORWARD_LOOKING_ENABLED, False),
    ),
    # PV-Prognose-Verzögerung
    MaestroSwitchDescription(
        key=CONF_PV_FORECAST_ENABLED,
        name="PV-Prognose-Verzögerung",
        icon="mdi:sun-clock",
        param_key=CONF_PV_FORECAST_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_PV_FORECAST_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_PV_FORECAST_ENABLED, False),
    ),
    # Schwacher-PV-Tag: Akku-Priorität an bewölkten Tagen
    MaestroSwitchDescription(
        key=CONF_LOW_YIELD_PRIORITY_ENABLED,
        name="Schwacher-PV-Tag-Priorität",
        icon="mdi:weather-cloudy-clock",
        param_key=CONF_LOW_YIELD_PRIORITY_ENABLED,
        on_fn=lambda coord: coord.update_param(CONF_LOW_YIELD_PRIORITY_ENABLED, True),
        off_fn=lambda coord: coord.update_param(CONF_LOW_YIELD_PRIORITY_ENABLED, False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MaestroSwitch(coordinator, desc) for desc in SWITCH_DESCRIPTIONS
    )


class MaestroSwitch(CoordinatorEntity[E3DCMaestroCoordinator], SwitchEntity):
    entity_description: MaestroSwitchDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: E3DCMaestroCoordinator, description: MaestroSwitchDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def is_on(self) -> bool:
        key = self.entity_description.key
        if key == "regelung_aktiv":
            return self.coordinator.regelung_aktiv
        if key == "force_discharge":
            return self.coordinator.force_discharge
        if key == "debug":
            return self.coordinator.debug_enabled
        if self.entity_description.param_key:
            return bool(getattr(self.coordinator._params, self.entity_description.param_key, False))
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.entity_description.on_fn(self.coordinator)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.entity_description.off_fn(self.coordinator)
        self.async_write_ha_state()
