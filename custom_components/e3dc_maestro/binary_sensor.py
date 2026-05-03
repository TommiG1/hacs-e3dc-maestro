"""Binary sensor platform for E3DC Maestro."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    PHASE_CURTAILMENT_GUARD,
    PHASE_EMERGENCY,
    PHASE_FEED_IN_LIMIT,
    PHASE_HT_PROTECTION,
)
from .coordinator import E3DCMaestroCoordinator
from .sensor import _device_info


@dataclass(frozen=True, kw_only=True)
class MaestroBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Any = None


BINARY_SENSOR_DESCRIPTIONS: tuple[MaestroBinarySensorDescription, ...] = (
    MaestroBinarySensorDescription(
        key="e3dc_reachable",
        name="E3DC erreichbar",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda coord: coord.last_update_success,
    ),
    MaestroBinarySensorDescription(
        key="feed_in_limit_active",
        name="Einspeisedrosselung aktiv",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda coord: coord.last_phase == PHASE_FEED_IN_LIMIT,
    ),
    MaestroBinarySensorDescription(
        key="ht_protection_active",
        name="HT-Schutz aktiv",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda coord: coord.last_phase == PHASE_HT_PROTECTION,
    ),
    MaestroBinarySensorDescription(
        key="emergency_charge_active",
        name="Notfallladung aktiv",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda coord: coord.last_phase == PHASE_EMERGENCY,
    ),
    MaestroBinarySensorDescription(
        key="curtailment_guard_active",
        name="Abregelschutz aktiv",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda coord: coord._curtailment_guard_active,
    ),
    MaestroBinarySensorDescription(
        key="charge_block_active",
        name="Ladesperre aktiv",
        icon="mdi:battery-lock",
        value_fn=lambda coord: bool(
            coord.last_decision
            and coord.last_decision.charge_power_limit is not None
            and coord.last_decision.charge_power_limit <= 0
        ),
    ),
    MaestroBinarySensorDescription(
        key="discharge_block_active",
        name="Entladesperre aktiv",
        icon="mdi:battery-off",
        value_fn=lambda coord: bool(
            coord.last_decision
            and coord.last_decision.discharge_power_limit is not None
            and coord.last_decision.discharge_power_limit <= 0
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MaestroBinarySensor(coordinator, desc) for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class MaestroBinarySensor(CoordinatorEntity[E3DCMaestroCoordinator], BinarySensorEntity):
    entity_description: MaestroBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: E3DCMaestroCoordinator, description: MaestroBinarySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)
