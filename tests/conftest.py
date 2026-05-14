"""Stub out homeassistant and other HA-only packages so control_engine/const can be tested."""
import sys
import types


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
    ("homeassistant.util.dt", {"utcnow": __import__("datetime").datetime.utcnow}),
    ("homeassistant.components.recorder", {}),
    ("homeassistant.components.recorder.statistics", {}),
]

for _name, _attrs in _HA_STUBS:
    sys.modules.setdefault(_name, _auto(_name, **_attrs))

# battery_sizing.py does `from homeassistant.util import dt as dt_util`, which
# goes through the homeassistant.util module object, not sys.modules directly.
# Explicitly wire the submodule as an attribute so the import resolves correctly.
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]  # type: ignore[attr-defined]

