#!/usr/bin/env python3
"""Validate Maestro dashboard YAML files for structural drift.

Checks:
  - required top-level views exist
  - entity_id references look like HA entity IDs
  - help navigation paths stay within the dashboard slug
  - shared section titles appear in both classic and modern dashboards
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "dashboards" / "maestro_dashboard.yaml"
MODERN = ROOT / "dashboards" / "maestro_dashboard_modern.yaml"

SHARED_MARKERS = (
    "Gesamt über Forecast-Zeitraum",
    "Auto-Optimierung",
    "Entscheidungserklärung",
)

STRATEGY_JSON = (
    ROOT / "custom_components" / "e3dc_maestro" / "frontend" / "maestro_dashboard.json"
)
STRATEGY_JS = (
    ROOT
    / "custom_components"
    / "e3dc_maestro"
    / "frontend"
    / "e3dc-maestro-strategy.js"
)

ENTITY_RE = re.compile(
    r"\b(?:sensor|binary_sensor|switch|number|select|button)\.[a-z0-9_]+\b"
)


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return {"_raw": text}
    return yaml.safe_load(text)


def _collect_titles(node, out: set[str]) -> None:
    if isinstance(node, dict):
        title = node.get("title") or node.get("heading")
        if isinstance(title, str):
            out.add(title)
        for v in node.values():
            _collect_titles(v, out)
    elif isinstance(node, list):
        for item in node:
            _collect_titles(item, out)


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if "views:" not in text and "title:" not in text:
        errors.append(f"{path.name}: missing views/title")
    # Entity-looking strings
    for m in ENTITY_RE.finditer(text):
        ent = m.group(0)
        if ".." in ent or ent.endswith("."):
            errors.append(f"{path.name}: bad entity id {ent}")
    # Broken absolute help paths that leave the dashboard
    if re.search(r"path:\s*/lovelace/", text):
        errors.append(f"{path.name}: unexpected /lovelace/ navigation path")
    return errors


def validate_strategy_assets() -> list[str]:
    """Ensure the community-strategy JSON stays in sync with classic YAML."""
    errors: list[str] = []
    if not STRATEGY_JS.exists():
        errors.append(f"missing {STRATEGY_JS.relative_to(ROOT)}")
    else:
        js = STRATEGY_JS.read_text(encoding="utf-8")
        if "customStrategies" not in js:
            errors.append("strategy JS missing customStrategies registration")
        if "e3dc-maestro" not in js:
            errors.append("strategy JS missing strategy type e3dc-maestro")
        if "maestro_dashboard.json" not in js:
            errors.append("strategy JS missing JSON asset reference")

    if not STRATEGY_JSON.exists():
        errors.append(f"missing {STRATEGY_JSON.relative_to(ROOT)}")
        return errors

    if yaml is None:
        errors.append("PyYAML required to validate strategy JSON sync")
        return errors

    classic = yaml.safe_load(CLASSIC.read_text(encoding="utf-8"))
    asset = json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))
    if classic != asset:
        errors.append(
            "strategy JSON out of sync with classic YAML – run "
            "python scripts/sync_dashboard_strategy.py"
        )
    elif not isinstance(asset, dict) or "views" not in asset:
        errors.append("strategy JSON missing views")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-shared", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    for path in (CLASSIC, MODERN):
        if not path.exists():
            errors.append(f"missing {path}")
            continue
        errors.extend(validate_file(path))

    if args.strict_shared and CLASSIC.exists() and MODERN.exists():
        classic_text = CLASSIC.read_text(encoding="utf-8")
        modern_text = MODERN.read_text(encoding="utf-8")
        for marker in SHARED_MARKERS:
            if marker not in classic_text:
                errors.append(f"classic missing shared marker: {marker}")
            if marker not in modern_text:
                errors.append(f"modern missing shared marker: {marker}")

    if CLASSIC.exists():
        errors.extend(validate_strategy_assets())

    if errors:
        print("Dashboard validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("Dashboard validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
