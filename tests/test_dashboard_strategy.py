"""Tests for the embedded Lovelace community dashboard strategy assets."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FRONTEND = ROOT / "custom_components" / "e3dc_maestro" / "frontend"
STRATEGY_JS = FRONTEND / "e3dc-maestro-strategy.js"
STRATEGY_JSON = FRONTEND / "maestro_dashboard.json"
CLASSIC_YAML = ROOT / "dashboards" / "maestro_dashboard.yaml"


def test_strategy_js_registers_community_dashboard() -> None:
    text = STRATEGY_JS.read_text(encoding="utf-8")
    assert 'const STRATEGY_TYPE = "e3dc-maestro"' in text
    assert "window.customStrategies" in text
    assert "strategyType: \"dashboard\"" in text
    assert "ll-strategy-dashboard-${STRATEGY_TYPE}" in text
    assert "maestro_dashboard.json" in text
    assert "getCreateSuggestions" in text
    assert "type: STRATEGY_TYPE" in text
    assert "E3DC Maestro" in text


def test_strategy_json_matches_classic_yaml() -> None:
    import yaml

    classic = yaml.safe_load(CLASSIC_YAML.read_text(encoding="utf-8"))
    asset = json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))
    assert classic == asset
    assert isinstance(asset.get("views"), list)
    assert len(asset["views"]) >= 10


def test_dashboard_frontend_module_and_assets() -> None:
    module = (
        ROOT / "custom_components" / "e3dc_maestro" / "dashboard_frontend.py"
    ).read_text(encoding="utf-8")
    assert 'DOMAIN, VERSION' in module or "from .const import DOMAIN, VERSION" in module
    assert "async_register_static_paths" in module
    assert "add_extra_js_url" in module
    assert '/{DOMAIN}/frontend' in module or 'f"/{DOMAIN}/frontend"' in module
    assert STRATEGY_JS.is_file()
    assert STRATEGY_JSON.is_file()
    init_py = (ROOT / "custom_components" / "e3dc_maestro" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "async_setup_frontend" in init_py
    assert "async def async_setup(" in init_py
    manifest = json.loads(
        (ROOT / "custom_components" / "e3dc_maestro" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert "frontend" in manifest["dependencies"]
    assert "http" in manifest["dependencies"]
    assert "lovelace" in manifest["after_dependencies"]
