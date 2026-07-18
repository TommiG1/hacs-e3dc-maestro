#!/usr/bin/env python3
"""Sync Classic dashboard YAML into the frontend strategy JSON asset.

Source of truth: dashboards/maestro_dashboard.yaml
Generated asset: custom_components/e3dc_maestro/frontend/maestro_dashboard.json

Usage:
  python scripts/sync_dashboard_strategy.py
  python scripts/sync_dashboard_strategy.py --check   # exit 1 if out of sync
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboards" / "maestro_dashboard.yaml"
DST = ROOT / "custom_components" / "e3dc_maestro" / "frontend" / "maestro_dashboard.json"


def _load_yaml() -> dict:
    data = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "views" not in data:
        raise SystemExit(f"{SRC.name}: expected mapping with 'views'")
    return data


def _render_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated JSON differs from the committed asset",
    )
    args = parser.parse_args()

    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1

    rendered = _render_json(_load_yaml())

    if args.check:
        if not DST.exists():
            print(f"missing asset {DST}", file=sys.stderr)
            return 1
        current = DST.read_text(encoding="utf-8")
        if current != rendered:
            print(
                "Dashboard strategy asset out of sync. Run:\n"
                "  python scripts/sync_dashboard_strategy.py",
                file=sys.stderr,
            )
            return 1
        print("Dashboard strategy asset OK")
        return 0

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(rendered, encoding="utf-8")
    print(f"Wrote {DST.relative_to(ROOT)} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
