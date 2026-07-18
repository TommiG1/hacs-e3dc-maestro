"""Shared device metadata for E3DC Maestro entities."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, VERSION

if TYPE_CHECKING:
    from .coordinator import E3DCMaestroCoordinator


def device_info(coordinator: E3DCMaestroCoordinator) -> dict:
    """Return Home Assistant device_info for all Maestro platforms."""
    return {
        "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
        "name": "E3DC Maestro",
        "manufacturer": "E3DC Maestro",
        "model": "Charge Orchestrator",
        "sw_version": VERSION,
    }
