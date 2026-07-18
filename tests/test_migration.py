"""Lightweight migration / device-metadata unit tests (no full HA runtime)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.e3dc_maestro import async_migrate_entry
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


def test_device_info_uses_manifest_version():
    coord = SimpleNamespace(entry=SimpleNamespace(entry_id="abc"))
    info = device_info(coord)
    assert info["sw_version"] == VERSION
    assert info["sw_version"] != "0.1.5"
