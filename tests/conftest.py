"""Stub out homeassistant and other HA-only packages so control_engine/const can be tested."""
import sys
import types
from dataclasses import dataclass
from typing import Any


class _AutoModule(types.ModuleType):
    """A module that returns a dummy class/value for any attribute access."""

    def __getattr__(self, name: str):
        # Return a generic class that can be used as a base class or called
        cls = type(name, (), {
            "__init__": lambda self, *a, **kw: None,
            "__class_getitem__": classmethod(lambda cls, item: cls),
        })
        setattr(self, name, cls)
        return cls


def _auto(name: str, **attrs) -> _AutoModule:
    mod = _AutoModule(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


class _Platform:
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    SWITCH = "switch"
    BUTTON = "button"


_HA_STUBS = [
    ("homeassistant", {}),
    ("homeassistant.config_entries", {"ConfigEntry": object}),
    ("homeassistant.const", {"Platform": _Platform}),
    ("homeassistant.core", {"callback": lambda f: f}),
    ("homeassistant.exceptions", {"ConfigEntryNotReady": Exception}),
    ("homeassistant.helpers", {}),
    (
        "homeassistant.helpers.config_validation",
        {"config_entry_only_config_schema": lambda _domain: {}},
    ),
    ("homeassistant.helpers.entity", {}),
    ("homeassistant.helpers.entity_platform", {}),
    ("homeassistant.helpers.entity_registry", {}),
    ("homeassistant.helpers.selector", {}),
    ("homeassistant.helpers.storage", {"Store": object}),
    ("homeassistant.helpers.update_coordinator", {}),
    ("homeassistant.components", {}),
    ("homeassistant.components.sensor", {}),
    ("homeassistant.components.binary_sensor", {}),
    ("homeassistant.components.number", {}),
    ("homeassistant.components.select", {}),
    ("homeassistant.components.switch", {}),
    ("homeassistant.components.button", {}),
    ("homeassistant.util", {}),
    ("homeassistant.util.dt", {
        "utcnow": __import__("datetime").datetime.utcnow,
        "now": __import__("datetime").datetime.now,
        "UTC": __import__("datetime").timezone.utc,
        "as_local": lambda dt: dt,
    }),
    ("homeassistant.components.recorder", {}),
    ("homeassistant.components.recorder.statistics", {}),
]

for _name, _attrs in _HA_STUBS:
    sys.modules.setdefault(_name, _auto(_name, **_attrs))

# homeassistant.const stubs need EntityCategory for sensor platform imports
sys.modules["homeassistant.const"].EntityCategory = type(  # type: ignore[attr-defined]
    "EntityCategory",
    (),
    {"DIAGNOSTIC": "diagnostic", "CONFIG": "config"},
)
sys.modules["homeassistant.const"].UnitOfEnergy = type(  # type: ignore[attr-defined]
    "UnitOfEnergy", (), {"KILO_WATT_HOUR": "kWh"}
)
sys.modules["homeassistant.const"].UnitOfPower = type(  # type: ignore[attr-defined]
    "UnitOfPower", (), {"WATT": "W"}
)
sys.modules["homeassistant.const"].STATE_UNAVAILABLE = "unavailable"  # type: ignore[attr-defined]
sys.modules["homeassistant.const"].STATE_UNKNOWN = "unknown"  # type: ignore[attr-defined]

# sensor component stubs used by sensor.py imports in migration tests.
# SensorEntityDescription must be a real (frozen, kw_only) dataclass with the
# fields sensor.py actually sets, since MaestroSensorDescription subclasses it
# via @dataclass(frozen=True, kw_only=True) — dataclass() only picks up fields
# declared on dataclass bases, a plain object base would silently drop them
# from the generated __init__ signature.
@dataclass(frozen=True, kw_only=True)
class _SensorEntityDescriptionStub:
    key: str = ""
    name: Any = None
    icon: Any = None
    device_class: Any = None
    native_unit_of_measurement: Any = None
    state_class: Any = None
    options: Any = None
    entity_category: Any = None


_sensor_mod = sys.modules["homeassistant.components.sensor"]
# Note: _sensor_mod is an _AutoModule, whose __getattr__ auto-vivifies (and
# caches) a dummy attribute on first access — so a `hasattr()` guard here
# would already see the dummy and skip assignment. Always set explicitly.
_sensor_mod.SensorEntityDescription = _SensorEntityDescriptionStub
_sensor_mod.SensorDeviceClass = type(
    "SensorDeviceClass",
    (),
    {
        "ENUM": "enum",
        "POWER": "power",
        "BATTERY": "battery",
        "ENERGY": "energy",
        "MONETARY": "monetary",
    },
)
_sensor_mod.SensorStateClass = type(
    "SensorStateClass",
    (),
    {
        "MEASUREMENT": "measurement",
        "TOTAL": "total",
        "TOTAL_INCREASING": "total_increasing",
    },
)
_sensor_mod.SensorEntity = type("SensorEntity", (), {"__init__": lambda self, *a, **k: None})

# battery_sizing.py does `from homeassistant.util import dt as dt_util`, which
# goes through the homeassistant.util module object, not sys.modules directly.
# Explicitly wire the submodule as an attribute so the import resolves correctly.
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]  # type: ignore[attr-defined]
sys.modules["homeassistant.helpers"].config_validation = sys.modules[  # type: ignore[attr-defined]
    "homeassistant.helpers.config_validation"
]
