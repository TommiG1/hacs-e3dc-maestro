"""Tests for the stable PV/house/grid/battery power mirror sensors.

These sensors give dashboards (e.g. the ApexCharts history chart) installation-
independent entity_ids, mirroring the normalised MaestroState values instead of
requiring users to hardcode their own E3DC raw sensor names.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.e3dc_maestro.control_engine import MaestroState
from custom_components.e3dc_maestro.sensor import SENSOR_DESCRIPTIONS, MaestroSensor

_MIRROR_KEYS = {
    "pv_power": "e3dc_maestro_pv_power",
    "house_power": "e3dc_maestro_house_power",
    "grid_power": "e3dc_maestro_grid_power",
    "battery_power": "e3dc_maestro_battery_power",
}


def _description(key: str):
    for desc in SENSOR_DESCRIPTIONS:
        if desc.key == key:
            return desc
    raise AssertionError(f"no SENSOR_DESCRIPTIONS entry for key={key!r}")


def _make_state(**overrides) -> MaestroState:
    base = dict(
        soc=55.0,
        pv_power=2500.0,
        house_power=600.0,
        grid_power=-100.0,
        battery_power=1800.0,
    )
    base.update(overrides)
    return MaestroState(**base)


def _make_coord(state: MaestroState | None):
    return SimpleNamespace(data={"state": state} if state is not None else None)


def test_mirror_descriptions_have_stable_object_id():
    for key, expected_object_id in _MIRROR_KEYS.items():
        desc = _description(key)
        assert desc.stable_object_id == expected_object_id


def test_mirror_sensor_entity_id_is_pinned_on_init():
    coordinator = SimpleNamespace(
        entry=SimpleNamespace(entry_id="abc123"),
        data=None,
    )
    for key, expected_object_id in _MIRROR_KEYS.items():
        desc = _description(key)
        entity = MaestroSensor(coordinator, desc)
        assert entity.entity_id == f"sensor.{expected_object_id}"
        assert entity._attr_unique_id == f"abc123_{key}"


def test_mirror_sensor_value_fn_reads_normalised_state():
    state = _make_state()
    coord = _make_coord(state)
    assert _description("pv_power").value_fn(coord) == state.pv_power
    assert _description("house_power").value_fn(coord) == state.house_power
    assert _description("grid_power").value_fn(coord) == state.grid_power
    assert _description("battery_power").value_fn(coord) == state.battery_power


def test_mirror_sensor_value_fn_returns_none_without_state():
    coord = _make_coord(None)
    for key in _MIRROR_KEYS:
        assert _description(key).value_fn(coord) is None


def test_current_soc_mirror_unchanged():
    """Guard against accidentally touching the pre-existing SoC mirror entity_id."""
    desc = _description("current_soc")
    assert desc.stable_object_id is None
    coordinator = SimpleNamespace(entry=SimpleNamespace(entry_id="abc123"), data=None)
    entity = MaestroSensor(coordinator, desc)
    # No stable_object_id set -> entity_id is never explicitly assigned, so HA
    # derives it from the (translatable) display name, exactly as before this
    # change.
    assert "entity_id" not in vars(entity)
