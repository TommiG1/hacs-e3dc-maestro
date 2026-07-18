"""Home Assistant diagnostics for E3DC Maestro config entries."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (redacted)."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    options = dict(entry.options)

    # Redact entity IDs that may be considered private installation details?
    # Keep entity IDs — they are needed for support — but strip free-form
    # service/action payloads that may contain secrets.
    redacted_options = dict(options)
    for key in list(redacted_options):
        if "service" in key or key.endswith("_token") or "password" in key:
            redacted_options[key] = "**REDACTED**"

    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "domain": entry.domain,
        },
        "options": redacted_options,
    }
    if coordinator is None:
        data["coordinator"] = None
        return data

    decision = coordinator.last_decision
    data["coordinator"] = {
        "regelung_aktiv": coordinator.regelung_aktiv,
        "last_phase": coordinator.last_phase,
        "forecast_pv_source": getattr(coordinator, "_forecast_pv_source", None),
        "auto_mode_enabled": coordinator._params.auto_mode_enabled,
        "auto_last_run": (
            coordinator._auto_last_run.isoformat()
            if getattr(coordinator, "_auto_last_run", None)
            else None
        ),
        "auto_run_failed": getattr(coordinator, "_auto_run_failed", False),
        "horizon_hint": (
            getattr(coordinator._auto_result, "horizon_h", None)
            if getattr(coordinator, "_auto_result", None)
            else None
        ),
        "last_decision": (
            {
                "phase": decision.phase,
                "reason": decision.reason,
                "charge_power_limit": decision.charge_power_limit,
                "discharge_power_limit": decision.discharge_power_limit,
                "power_mode": decision.power_mode,
            }
            if decision
            else None
        ),
        "sent_limits": {
            "charge": coordinator.last_sent_charge_limit,
            "discharge": coordinator.last_sent_discharge_limit,
        },
        "rscp_ok": coordinator._last_rscp_act_ok,
        "consecutive_failures": coordinator._consecutive_failures,
        "consecutive_rscp_failures": coordinator._consecutive_rscp_failures,
    }
    return data
