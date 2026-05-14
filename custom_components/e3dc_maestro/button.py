"""Button platform for E3DC Maestro."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, E3DC_RSCP_DOMAIN, SERVICE_CLEAR_POWER_LIMITS, SERVICE_MANUAL_CHARGE
from .coordinator import E3DCMaestroCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MaestroClearLimitsButton(coordinator),
        MaestroManualChargeButton(coordinator),
        MaestroResetStatsButton(coordinator),
        MaestroRunSizingButton(coordinator),
    ])


class MaestroClearLimitsButton(CoordinatorEntity[E3DCMaestroCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Limits jetzt freigeben"
    _attr_icon = "mdi:lock-open-variant"

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_clear_limits"
        self._attr_device_info = _device_info(coordinator)

    async def async_press(self) -> None:
        await self.coordinator._async_release_limits("Manuell über Button")


class MaestroManualChargeButton(CoordinatorEntity[E3DCMaestroCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Manuell laden (3 kWh)"
    _attr_icon = "mdi:battery-charging-wireless"

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_manual_charge"
        self._attr_device_info = _device_info(coordinator)

    async def async_press(self) -> None:
        if self.coordinator._can_manual_charge():
            await self.coordinator._call_e3dc(
                SERVICE_MANUAL_CHARGE, {"charge_amount": 3000}
            )
            from homeassistant.util import dt as dt_util
            self.coordinator._last_manual_charge = dt_util.utcnow()
            self.coordinator._log("Manuelles Laden via Button ausgelöst")


class MaestroResetStatsButton(CoordinatorEntity[E3DCMaestroCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Statistik zurücksetzen"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reset_stats"
        self._attr_device_info = _device_info(coordinator)

    async def async_press(self) -> None:
        for key in self.coordinator.stats:
            self.coordinator.stats[key] = 0.0
        self.coordinator._log("Statistik manuell zurückgesetzt")
        await self.coordinator._async_save_stats()


class MaestroRunSizingButton(CoordinatorEntity[E3DCMaestroCoordinator], ButtonEntity):
    """Trigger a new Battery & PV Sizing analysis run."""

    _attr_has_entity_name = True
    _attr_name = "Sizing-Analyse starten"
    _attr_icon = "mdi:chart-timeline-variant-shimmer"

    def __init__(self, coordinator: E3DCMaestroCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_run_sizing"
        self._attr_device_info = _device_info(coordinator)

    async def async_press(self) -> None:
        await self.coordinator.async_run_sizing_analysis()
