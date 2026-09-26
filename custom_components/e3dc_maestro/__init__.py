"""E3DC Maestro – charge orchestration for E3DC storage systems."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, E3DC_RSCP_DOMAIN
from .coordinator import E3DCMaestroCoordinator

_LOGGER = logging.getLogger(__name__)

# Entity-ID-Migration: `sensor.py` hat den Anzeigenamen dieser Sensoren mehrfach
# umbenannt (z. B. "Aktives Lade-Limit" -> "Soll-Lade-Limit"). Home Assistant
# ändert die entity_id dabei NIE automatisch mit – nur der Anzeigename und die
# unique_id (die am `key=` hängt) folgen dem Code. Bestandsinstallationen
# bleiben also auf der alten entity_id sitzen, während Neuinstallationen die
# neue bekommen. Dashboards können immer nur eine der beiden ID referenzieren
# (siehe GitHub-Issue #3). Diese Migration zieht bestehende Installationen auf
# die ID nach, die auch eine Neuinstallation heute bekommen würde.
_ENTITY_ID_RENAMES: dict[str, str] = {
    # unique_id-Suffix (== SensorEntityDescription.key) -> Ziel-Object-ID
    "charge_power_limit": "soll_lade_limit",
    "discharge_power_limit": "soll_entlade_limit",
    "feed_in_avoided_today": "dc_abregelung_verhindert_heute",
}


async def _async_migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename stale entity_ids left behind by past `name=` renames in sensor.py."""
    ent_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        prefix = f"{entry.entry_id}_"
        if not entity_entry.unique_id.startswith(prefix):
            continue
        key = entity_entry.unique_id[len(prefix):]
        new_object_id = _ENTITY_ID_RENAMES.get(key)
        if new_object_id is None:
            continue

        domain = entity_entry.entity_id.split(".", 1)[0]
        new_entity_id = f"{domain}.e3dc_maestro_{new_object_id}"
        if entity_entry.entity_id == new_entity_id:
            continue
        if ent_reg.async_get(new_entity_id) is not None:
            _LOGGER.warning(
                "E3DC Maestro: kann %s nicht nach %s migrieren – Ziel-entity_id "
                "ist bereits belegt",
                entity_entry.entity_id,
                new_entity_id,
            )
            continue

        _LOGGER.info(
            "E3DC Maestro: migriere entity_id %s -> %s (Dashboard-Rename-Nachzug)",
            entity_entry.entity_id,
            new_entity_id,
        )
        ent_reg.async_update_entity(entity_entry.entity_id, new_entity_id=new_entity_id)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Maestro is configured exclusively through its Config Flow.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration domain (once) and register the dashboard strategy."""
    del config  # unused – config-entry only
    from .dashboard_frontend import async_setup_frontend

    await async_setup_frontend(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current schema version."""
    _LOGGER.debug("Migrating E3DC Maestro entry from version %s", entry.version)

    if entry.version < 2:
        # Phase B: power_factor removed – drop it from stored options
        new_options = dict(entry.options)
        new_options.pop("power_factor", None)
        hass.config_entries.async_update_entry(entry, options=new_options, version=2)
        _LOGGER.info("Migrated E3DC Maestro config entry to version 2 (power_factor removed)")

    if entry.version < 3:
        # v0.3.1: spreading_enabled wird zum Hardware-Schutz-Default.
        # Bestehende Installationen, die den Schalter nie explizit gesetzt haben
        # (oder ihn auf False stehen haben), werden auf True umgestellt, damit
        # die Auto-Lade-Bursts (0 W ↔ max_charge_power) nicht weiter Hardware
        # stressen. Wer das bewusst nicht möchte, kann den Switch im UI wieder
        # ausschalten.
        new_options = dict(entry.options)
        if not new_options.get("spreading_enabled", False):
            new_options["spreading_enabled"] = True
            _LOGGER.info(
                "E3DC Maestro v0.3.1: Spreading (Ladeverteilung) automatisch "
                "aktiviert – schützt die Hardware vor 0/max-Lade-Bursts. "
                "Kann im UI deaktiviert werden."
            )
        hass.config_entries.async_update_entry(entry, options=new_options, version=3)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up E3DC Maestro from a config entry."""
    # Verify that e3dc_rscp is configured
    if not hass.config_entries.async_entries(E3DC_RSCP_DOMAIN):
        raise ConfigEntryNotReady(
            f"E3DC Maestro requires the '{E3DC_RSCP_DOMAIN}' integration to be "
            "configured first. Please add the E3DC RSCP integration and restart."
        )

    # Ensure strategy is available even if async_setup was skipped (edge cases).
    from .dashboard_frontend import async_setup_frontend

    await async_setup_frontend(hass)
    await _async_migrate_entity_ids(hass, entry)

    coordinator = E3DCMaestroCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update – reload so entities pick up new settings.

    Skipped when the change came from a live entity toggle (coordinator sets
    ``skip_reload`` around ``async_update_entry`` calls for that).
    """
    from .coordinator import E3DCMaestroCoordinator
    coordinator: E3DCMaestroCoordinator | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id)
    )
    if coordinator is not None and coordinator.skip_reload:
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload E3DC Maestro config entry."""
    coordinator: E3DCMaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
