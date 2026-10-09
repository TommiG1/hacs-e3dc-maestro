"""Select platform for E3DC Maestro."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TARIFF_MODE,
    CONF_WALLBOX_TYPE,
    DEFAULT_TARIFF_MODE,
    TARIFF_MODES,
    CONF_MORNING_DISCHARGE_MODE,
    CONF_AUTO_MODE_OBJECTIVE,
    AUTO_MODE_OBJECTIVES,
    DEFAULT_AUTO_MODE_OBJECTIVE,
    DOMAIN,
    MORNING_DISCHARGE_ACTIVE_GRID,
    MORNING_DISCHARGE_ACTIVE_HOUSE,
    MORNING_DISCHARGE_OFF,
    MORNING_DISCHARGE_PASSIVE,
    WALLBOX_TYPE_E3DC,
    WALLBOX_TYPE_GENERIC,
)
from .coordinator import E3DCMaestroCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MaestroWallboxTypeSelect(coordinator),
        MaestroMorningDischargeModeSelect(coordinator),
        MaestroAutoModeObjectiveSelect(coordinator),
        MaestroTariffModeSelect(coordinator),
    ])


class MaestroWallboxTypeSelect(CoordinatorEntity[E3DCMaestroCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Wallbox-Typ"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_options = [WALLBOX_TYPE_E3DC, WALLBOX_TYPE_GENERIC]

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_wallbox_type"
        self._attr_device_info = _device_info(coordinator)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.entry.options.get(CONF_WALLBOX_TYPE, WALLBOX_TYPE_E3DC)

    async def async_select_option(self, option: str) -> None:
        self.coordinator.update_param(CONF_WALLBOX_TYPE, option)
        self.async_write_ha_state()


class MaestroMorningDischargeModeSelect(CoordinatorEntity[E3DCMaestroCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Vorentladungs-Modus"
    _attr_icon = "mdi:battery-arrow-down"
    _attr_options = [
        MORNING_DISCHARGE_OFF,
        MORNING_DISCHARGE_PASSIVE,
        MORNING_DISCHARGE_ACTIVE_HOUSE,
        MORNING_DISCHARGE_ACTIVE_GRID,
    ]

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_morning_discharge_mode"
        self._attr_device_info = _device_info(coordinator)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.entry.options.get(
            CONF_MORNING_DISCHARGE_MODE, MORNING_DISCHARGE_OFF
        )

    async def async_select_option(self, option: str) -> None:
        self.coordinator.update_param(CONF_MORNING_DISCHARGE_MODE, option)
        self.async_write_ha_state()


class MaestroAutoModeObjectiveSelect(CoordinatorEntity[E3DCMaestroCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Auto-Optimierung: Ziel"
    _attr_icon = "mdi:target"
    _attr_options = list(AUTO_MODE_OBJECTIVES)

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_auto_mode_objective"
        self._attr_device_info = _device_info(coordinator)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.entry.options.get(
            CONF_AUTO_MODE_OBJECTIVE, DEFAULT_AUTO_MODE_OBJECTIVE
        )

    async def async_select_option(self, option: str) -> None:
        self.coordinator.update_param(CONF_AUTO_MODE_OBJECTIVE, option)
        self.async_write_ha_state()


class MaestroTariffModeSelect(CoordinatorEntity[E3DCMaestroCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Tarif-Modus"
    _attr_icon = "mdi:cash-clock"
    _attr_options = list(TARIFF_MODES)

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_tariff_mode"
        self._attr_device_info = _device_info(coordinator)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.entry.options.get(CONF_TARIFF_MODE, DEFAULT_TARIFF_MODE)

    async def async_select_option(self, option: str) -> None:
        self.coordinator.update_param(CONF_TARIFF_MODE, option)
        self.async_write_ha_state()
