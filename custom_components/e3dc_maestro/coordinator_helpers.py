"""Pure helpers for the E3DC Maestro coordinator (no I/O).

Kept separate from ``coordinator.py`` so unit tests can cover timing,
debounce and forecast-cache logic without Home Assistant.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .const import (
    CONF_DYNAMIC_TARIFF_ENABLED,
    CONF_TARIFF_SLOTS,
    POWER_MODE_CHARGE,
    POWER_MODE_CHARGE_FROM_GRID,
    POWER_MODE_DISCHARGE,
    POWER_MODE_IDLE,
    POWER_MODE_NORMAL,
)
from .control_engine import (
    MaestroDecision,
    MaestroParams,
    TARIFF_HIGH,
    TARIFF_LOW,
    TARIFF_NORMAL,
    TariffSchedule,
    TariffSlot,
)
from .optimizer import run_optimizer


def energy_interval_hours(
    last_tick: datetime | None,
    now: datetime,
    update_interval: timedelta,
    *,
    max_factor: float = 3.0,
) -> float | None:
    """Return elapsed hours for energy integration, or None to skip this tick.

    First tick after start/restart returns ``None`` so we do not invent energy.
    Long gaps are clamped to ``max_factor × update_interval`` to avoid spikes.
    """
    if last_tick is None:
        return None
    elapsed_s = (now - last_tick).total_seconds()
    if elapsed_s <= 0:
        return None
    max_s = max(update_interval.total_seconds(), 1.0) * max_factor
    return min(elapsed_s, max_s) / 3600.0


def quarter_slot(now: datetime) -> datetime:
    """Floor *now* to the current 15-minute quarter (timezone preserved)."""
    base = now.replace(second=0, microsecond=0)
    return base.replace(minute=(base.minute // 15) * 15)


def forecast_input_fingerprint(
    *,
    soc: float,
    regelung_aktiv: bool,
    cons_h: list[float] | None,
    pv_h: list[float] | None,
    params_key: tuple[Any, ...],
    quarter: datetime,
) -> tuple[Any, ...]:
    """Stable cache key for the 24h forecast simulator."""
    return (
        round(soc, 1),
        regelung_aktiv,
        tuple(round(v, 1) for v in (cons_h or ())),
        tuple(round(v, 1) for v in (pv_h or ())),
        params_key,
        quarter.isoformat(),
    )


def forecast_target_date(now: datetime, days_ahead: int = 0):
    """Return the calendar date for a PV forecast day (0=today, 1=tomorrow)."""
    return (now + timedelta(days=days_ahead)).date()


_EWMA_GLITCH_ZERO_FLOOR_W: float = 200.0  # below this, 0-values are not glitches


def _ewma_update(
    prev: float | None,
    new_val: float,
    tau_s: float,
    dt_s: float,
    jump_threshold_w: float,
) -> float:
    """Exponential weighted moving average with jump-reset and zero-glitch guard.

    Falls der neue Wert mehr als *jump_threshold_w* vom Vorgänger abweicht
    (z.B. Wallbox-Start), wird der EWMA sofort auf den neuen Wert gesetzt
    statt träge nachzuführen.

    Zero-Glitch-Guard: Liefert der Sensor exakt 0 W, obwohl der bisherige
    EWMA deutlich über _EWMA_GLITCH_ZERO_FLOOR_W liegt, wird der Wert als
    E3DC-RSCP-Glitch verworfen und der vorherige EWMA-Wert beibehalten.
    """
    if prev is None:
        return new_val
    # Zero-Glitch-Guard: exakter 0-Wert bei laufendem Verbrauch = Sensor-Aussetzer
    if new_val == 0.0 and prev > _EWMA_GLITCH_ZERO_FLOOR_W:
        return prev
    if abs(new_val - prev) > jump_threshold_w:
        return new_val
    alpha = 1.0 - math.exp(-dt_s / max(tau_s, 1e-6))
    return prev + alpha * (new_val - prev)



# How much a power limit must change to trigger a new service call (W)
POWER_DEBOUNCE_W = 50



def _limits_changed_vs_sent_values(
    charge: float | None,
    discharge: float | None,
    last_sent_charge: int | None,
    last_sent_discharge: int | None,
    *,
    debounce_w: int = POWER_DEBOUNCE_W,
) -> bool:
    """Return True when limits differ enough from last RSCP call to resend."""
    if (last_sent_charge is None) != (charge is None):
        return True
    if (last_sent_discharge is None) != (discharge is None):
        return True
    if charge is not None and abs(
        int(round(charge)) - (last_sent_charge or 0)
    ) > debounce_w:
        return True
    if discharge is not None and abs(
        int(round(discharge)) - (last_sent_discharge or 0)
    ) > debounce_w:
        return True
    return False



def _ramp_bypass_due_to_resync(
    target_w: int,
    last_sent_w: int | None,
    ramp_w_per_cycle: int,
    *,
    min_threshold_w: int = 500,
) -> bool:
    """True wenn der Soll-Wert zu weit vom zuletzt gesendeten Cap abweicht.

    Ohne Bypass würde die Anlauf-Rampe nach einem Phasenwechsel oder einem
    Korridor-Dip (siehe :func:`control_engine.desired_charge_power`) zig
    Zyklen brauchen, bis das Cap wieder zum echten Bedarf passt. In der
    Zwischenzeit hängt die E3DC an einem veralteten, viel zu kleinen Cap
    (z. B. 51 W) und kann den PV-Überschuss nicht in den Akku speisen.
    """
    if last_sent_w is None:
        return False
    threshold = max(min_threshold_w, 2 * ramp_w_per_cycle)
    return abs(target_w - last_sent_w) > threshold



def _effective_discharge_limit_w(
    decision: MaestroDecision,
    max_battery_power_w: float,
) -> int | None:
    """Soll-Entlade-Cap (W) für Anzeige und RSCP-Send.

    ``decision.discharge_power_limit`` ist gesetzt → explizites Cap (z. B.
    EVCC Now 800 W oder 0 = Sperre). Sonst, wenn ein Lade-Cap aktiv ist,
    gilt Entladung als frei bis ``max_charge_power`` – muss an die E3DC
    gesendet werden, sonst bleibt eine frühere Entladesperre (z. B. nach
    EVCC) aktiv. Nicht ``inverter_power`` (WR-Nennleistung): die kann
    höher sein als die tatsächliche Akku-Leistungsgrenze.
    """
    if decision.discharge_power_limit is not None:
        return int(decision.discharge_power_limit)
    if decision.charge_power_limit is not None:
        return int(max_battery_power_w)
    return None



def _build_power_mode_data(
    power_mode: str,
    charge_power_limit: float | None,
    discharge_power_limit: float | None,
) -> dict[str, Any]:
    """Build the data dict for the e3dc_rscp ``set_power_mode`` service.

    ``power_value`` wird nur bei CHARGE/DISCHARGE mitgegeben. NORMAL und IDLE
    brauchen kein ``power_value`` – das eigentliche Lade-/Entlade-Cap setzt
    bereits ``set_power_limits`` (max_charge / max_discharge). Ein
    zusätzliches ``power_value`` im NORMAL-Modus hat im Feld zu unklarem
    Verhalten geführt (E3DC interpretiert je nach Firmware unterschiedlich).
    """
    data: dict[str, Any] = {"power_mode": power_mode}
    if power_mode == POWER_MODE_CHARGE and charge_power_limit is not None:
        # CHARGE-Mode verlangt strikt > 0 W.
        data["power_value"] = max(1, int(charge_power_limit))
    elif power_mode == POWER_MODE_DISCHARGE and discharge_power_limit is not None:
        data["power_value"] = max(1, int(discharge_power_limit))
    return data



E3DC_RSCP_POWER_MODE_MAP = {
    POWER_MODE_NORMAL: "0",
    POWER_MODE_IDLE: "1",
    POWER_MODE_DISCHARGE: "2",
    POWER_MODE_CHARGE: "3",
    POWER_MODE_CHARGE_FROM_GRID: "4",
}



def _params_from_options(options: dict[str, Any]) -> MaestroParams:
    """Build MaestroParams from config entry options."""
    p = MaestroParams()
    for attr in p.__dataclass_fields__:
        if attr in options:
            setattr(p, attr, options[attr])
    # Phase C: convert stored slot list (if any) into a TariffSchedule that
    # overrides the legacy ht_*/cheap_threshold conversion.
    schedule = _tariff_schedule_from_stored(options)
    if schedule is not None:
        p.tariff_schedule = schedule
    return p



_VALID_CLASSES = {TARIFF_HIGH, TARIFF_LOW, TARIFF_NORMAL}



def _tariff_schedule_from_stored(options: dict[str, Any]) -> TariffSchedule | None:
    """Parse ``options[CONF_TARIFF_SLOTS]`` into a :class:`TariffSchedule`.

    Returns ``None`` when no slot list is stored, so the legacy ``ht_*`` /
    cheap-threshold fallback in :func:`tariff_schedule_from_params` keeps
    working for unmigrated entries.
    """
    raw = options.get(CONF_TARIFF_SLOTS)
    if not raw:
        return None
    slots: list[TariffSlot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            weekdays = frozenset(int(d) for d in item.get("weekdays", []))
            start_h = float(item["start_h"])
            end_h = float(item["end_h"])
        except (KeyError, TypeError, ValueError):
            continue
        cls = item.get("class_") or item.get("class") or TARIFF_HIGH
        if cls not in _VALID_CLASSES:
            cls = TARIFF_HIGH
        reserve = item.get("min_reserve_soc")
        try:
            reserve_f = float(reserve) if reserve is not None else None
        except (TypeError, ValueError):
            reserve_f = None
        slots.append(
            TariffSlot(
                weekdays=weekdays,
                start_h=start_h,
                end_h=end_h,
                class_=cls,
                min_reserve_soc=reserve_f,
            )
        )
    if not slots:
        return None
    threshold = (
        float(options["cheap_threshold"])
        if options.get(CONF_DYNAMIC_TARIFF_ENABLED)
        and options.get("cheap_threshold") is not None
        else None
    )
    return TariffSchedule(slots=slots, cheap_threshold=threshold)



def _run_optimizer_sync(
    base_params,
    soc: float,
    cons_h: list,
    pv_h: list,
    battery_capacity_kwh: float,
    regelung_aktiv: bool,
    max_discharge_power: float,
    objective: str,
    now,
    consumption_data_days: int,
    pv_data_days: int,
    pv_h_day2: list[float] | None = None,
):
    """Thread-safe wrapper for run_optimizer (called via async_add_executor_job)."""
    return run_optimizer(
        base_params=base_params,
        soc=soc,
        consumption_h=cons_h,
        pv_h=pv_h,
        battery_capacity_kwh=battery_capacity_kwh,
        regelung_aktiv=regelung_aktiv,
        max_discharge_power=max_discharge_power,
        objective=objective,
        now=now,
        consumption_data_days=consumption_data_days,
        pv_data_days=pv_data_days,
        pv_h_day2=pv_h_day2,
        # Day-2 consumption: reuse the historic 7-day average (cons_h) since
        # we don't have weekday-specific intra-day forecasts yet.
        consumption_h_day2=cons_h if pv_h_day2 is not None else None,
    )

