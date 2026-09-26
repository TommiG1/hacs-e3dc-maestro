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


def _registry_entry(
    unique_id: str, entity_id: str, disabled_by: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        platform="e3dc_maestro",
        unique_id=unique_id,
        entity_id=entity_id,
        disabled_by=disabled_by,
    )


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


@pytest.mark.asyncio
async def test_migrate_reenables_dashboard_sensors_disabled_by_integration(monkeypatch):
    """Issue #3: dashboard cards stayed empty because these shipped disabled."""
    entry = SimpleNamespace(entry_id="abc123")
    debug_log = _registry_entry(
        "abc123_debug_log", "sensor.e3dc_maestro_debug_log", disabled_by="integration"
    )
    avoided = _registry_entry(
        "abc123_curtailment_avoided_today",
        "sensor.e3dc_maestro_abregelung_verhindert_heute",
        disabled_by="integration",
    )

    fake_registry = MagicMock()
    fake_registry.async_get.return_value = None
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[debug_log, avoided]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_any_call(
        "sensor.e3dc_maestro_debug_log", disabled_by=None
    )
    fake_registry.async_update_entity.assert_any_call(
        "sensor.e3dc_maestro_abregelung_verhindert_heute", disabled_by=None
    )
    assert fake_registry.async_update_entity.call_count == 2


@pytest.mark.asyncio
async def test_migrate_respects_user_disabled_entities(monkeypatch):
    """A deliberate user opt-out must survive the update."""
    entry = SimpleNamespace(entry_id="abc123")
    user_disabled = _registry_entry(
        "abc123_debug_log", "sensor.e3dc_maestro_debug_log", disabled_by="user"
    )

    fake_registry = MagicMock()
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[user_disabled]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_leaves_already_enabled_sensors_alone(monkeypatch):
    """Idempotent: nothing to do once the sensor is enabled."""
    entry = SimpleNamespace(entry_id="abc123")
    enabled = _registry_entry("abc123_debug_log", "sensor.e3dc_maestro_debug_log")

    fake_registry = MagicMock()
    monkeypatch.setattr(
        maestro_init.er, "async_get", MagicMock(return_value=fake_registry), raising=False
    )
    monkeypatch.setattr(
        maestro_init.er,
        "async_entries_for_config_entry",
        MagicMock(return_value=[enabled]),
        raising=False,
    )

    await _async_migrate_entity_ids(MagicMock(), entry)

    fake_registry.async_update_entity.assert_not_called()


def test_intentionally_disabled_keys_match_the_platform_sources():
    """Guard the invariant: a `=False` flag must be listed, or it gets re-enabled.

    The platform modules need Python >= 3.10 (`dataclass(kw_only=True)`), so this
    reads the sources instead of importing them.
    """
    import re
    from pathlib import Path

    platform_dir = Path(maestro_init.__file__).parent
    flagged: set[str] = set()
    for name in ("sensor", "binary_sensor", "number", "switch", "select", "button"):
        source_file = platform_dir / f"{name}.py"
        if not source_file.exists():
            continue
        # Split on description constructors so each block holds one entity.
        for block in re.split(r"\w*Description\(", source_file.read_text())[1:]:
            key = re.search(r'key="([^"]+)"', block)
            if key and "entity_registry_enabled_default=False" in block[:1200]:
                flagged.add(key.group(1))

    assert flagged == set(maestro_init._KEYS_INTENTIONALLY_DISABLED), (
        "Entity descriptions with entity_registry_enabled_default=False must be "
        "listed in _KEYS_INTENTIONALLY_DISABLED, otherwise the migration "
        "re-enables them on every restart."
    )


def test_device_info_uses_manifest_version():
    coord = SimpleNamespace(entry=SimpleNamespace(entry_id="abc"))
    info = device_info(coord)
    assert info["sw_version"] == VERSION
    assert info["sw_version"] != "0.1.5"
