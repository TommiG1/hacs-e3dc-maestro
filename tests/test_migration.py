"""Lightweight migration / device-metadata unit tests (no full HA runtime)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import custom_components.e3dc_maestro as maestro_init
from custom_components.e3dc_maestro import _async_migrate_entity_ids, async_migrate_entry
from custom_components.e3dc_maestro.const import VERSION
from custom_components.e3dc_maestro.sensor_device import device_info


def _make_hass() -> MagicMock:
    hass = MagicMock()

    def _update_entry(_entry, **kwargs):
        if "options" in kwargs:
            _entry.options = kwargs["options"]
        if "version" in kwargs:
            _entry.version = kwargs["version"]

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update_entry)
    return hass


@pytest.mark.asyncio
async def test_migrate_v1_removes_power_factor():
    entry = SimpleNamespace(version=1, options={"power_factor": 1.2, "spreading_enabled": True})
    hass = _make_hass()
    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 3
    assert "power_factor" not in entry.options


@pytest.mark.asyncio
async def test_migrate_v2_enables_spreading_default():
    entry = SimpleNamespace(version=2, options={"spreading_enabled": False})
    hass = _make_hass()
    assert await async_migrate_entry(hass, entry) is True
    assert entry.options["spreading_enabled"] is True
    assert entry.version == 3


def _registry_entry(unique_id: str, entity_id: str) -> SimpleNamespace:
    return SimpleNamespace(platform="e3dc_maestro", unique_id=unique_id, entity_id=entity_id)


@pytest.mark.asyncio
async def test_migrate_entity_ids_renames_stale_ids(monkeypatch):
    """Issue #3: pre-rename installs keep 'aktives_*' entity_ids forever unless migrated."""
    entry = SimpleNamespace(entry_id="abc123")
    stale_charge = _registry_entry(
        "abc123_charge_power_limit", "sensor.e3dc_maestro_aktives_lade_limit"
    )
    stale_discharge = _registry_entry(
        "abc123_discharge_power_limit", "sensor.e3dc_maestro_aktives_entlade_limit"
    )
    unrelated = _registry_entry("abc123_current_soc", "sensor.e3dc_maestro_aktueller_soc")

    fake_registry = MagicMock()
    fake_registry.async_get.return_value = None  # target entity_id is free
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[stale_charge, stale_discharge, unrelated]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_any_call(
        "sensor.e3dc_maestro_aktives_lade_limit",
        new_entity_id="sensor.e3dc_maestro_soll_lade_limit",
    )
    fake_registry.async_update_entity.assert_any_call(
        "sensor.e3dc_maestro_aktives_entlade_limit",
        new_entity_id="sensor.e3dc_maestro_soll_entlade_limit",
    )
    assert fake_registry.async_update_entity.call_count == 2


@pytest.mark.asyncio
async def test_migrate_entity_ids_noop_when_already_current(monkeypatch):
    """Fresh installs already have the target id – migration must not touch them."""
    entry = SimpleNamespace(entry_id="abc123")
    fresh = _registry_entry(
        "abc123_charge_power_limit", "sensor.e3dc_maestro_soll_lade_limit"
    )

    fake_registry = MagicMock()
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[fresh]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_entity_ids_skips_on_collision(monkeypatch):
    """Never overwrite an existing entity that already owns the target entity_id."""
    entry = SimpleNamespace(entry_id="abc123")
    stale_charge = _registry_entry(
        "abc123_charge_power_limit", "sensor.e3dc_maestro_aktives_lade_limit"
    )

    fake_registry = MagicMock()
    fake_registry.async_get.return_value = SimpleNamespace()  # target already taken
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[stale_charge]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_not_called()


def test_device_info_uses_manifest_version():
    coord = SimpleNamespace(entry=SimpleNamespace(entry_id="abc"))
    info = device_info(coord)
    assert info["sw_version"] == VERSION
    assert info["sw_version"] != "0.1.5"
