"""Register the Lovelace community dashboard strategy with Home Assistant."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_STRATEGY_JS = "e3dc-maestro-strategy.js"
_STATIC_URL_BASE = f"/{DOMAIN}/frontend"
_SETUP_FLAG = f"{DOMAIN}_frontend_registered"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve strategy assets and preload the JS module once per HA instance."""
    if hass.data.get(_SETUP_FLAG):
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                _STATIC_URL_BASE,
                str(_FRONTEND_DIR),
                cache_headers=False,
            )
        ]
    )

    # Bust browser caches when the integration version changes.
    module_url = f"{_STATIC_URL_BASE}/{_STRATEGY_JS}?v={VERSION}"
    add_extra_js_url(hass, module_url)
    hass.data[_SETUP_FLAG] = True
    _LOGGER.debug("Registered E3DC Maestro dashboard strategy at %s", module_url)
