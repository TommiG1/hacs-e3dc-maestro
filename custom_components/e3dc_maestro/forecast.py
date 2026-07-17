"""F1: 24-hour battery SoC forecast simulator.

Uses the pure ``decide()`` function from the rule engine to step through
the next 24 hours and estimate the battery state of charge trajectory,
grid exchange and self-sufficiency.

The simulation is deterministic and runs fully in-process without I/O,
so it can be called from both the coordinator and the F3 optimizer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .const import (
    PHASE_MORNING_DISCHARGE,
    POWER_MODE_CHARGE,
    POWER_MODE_CHARGE_FROM_GRID,
    POWER_MODE_DISCHARGE,
    POWER_MODE_IDLE,
    POWER_MODE_NORMAL,
)
from .control_engine import MaestroDecision, MaestroParams, MaestroState, decide

if TYPE_CHECKING:
    pass


@dataclass
class ForecastResult:
    """Result of a 24-hour simulation (96 quarter-hour steps internally)."""

    # SoC values after each simulated step.
    # len=96 for quarter-hour resolution, len=24 for legacy hourly callers.
    trajectory_soc: list[float]
    trajectory_hours: list[int]          # UTC hour-of-day for each step
    trajectory_phases: list[str]         # phase returned by decide() per step

    min_soc: float                       # min SoC over 24h
    max_soc: float                       # max SoC over 24h

    grid_draw_kwh: float                 # total kWh drawn from grid (>0 = bad)
    grid_feed_in_kwh: float              # total kWh fed into grid (>0 = good)

    # Fraction of house consumption covered without drawing from grid (0–1)
    self_sufficiency: float | None = None

    # PV lost due to full battery + feed-in cap
    pv_curtailed_kwh: float = 0.0

    # Cost accounting (€) — populated when price_q or fixed_buy_price is available
    cost_eur: float = 0.0       # total grid-buy cost
    revenue_eur: float = 0.0    # total feed-in revenue

    # Absolute battery energy moved (|charge| + |discharge|) over the horizon
    battery_throughput_kwh: float = 0.0


def simulate_next_24h(
    *,
    soc: float,
    consumption_h: list[float],  # 24 hourly mean W values indexed by UTC hour-of-day
    pv_h: list[float],            # 24/48/96 mean W values (hourly/30-min/15-min, UTC)
    params: MaestroParams,
    now: datetime,
    battery_capacity_kwh: float = 15.0,
    regelung_aktiv: bool = True,
    max_discharge_power: float | None = None,
    price_q: list[float] | None = None,  # 96 quarter-hour buy prices (€/kWh); dynamic tariff
    pv_h_day2: list[float] | None = None,        # 24/48/96 W for the day after
    consumption_h_day2: list[float] | None = None,  # 24 hourly W for the day after
    horizon_h: int = 24,                          # 24 or 48
) -> ForecastResult:
    """Simulate the next 24 hours in 15-minute steps (96 quarters) starting from *soc* %.

    Parameters
    ----------
    soc:
        Starting state of charge in percent (0–100).
    consumption_h:
        Average house consumption for each UTC hour of the day (W), len=24.
        Quarter-hour values are derived by repetition within each hour.
    pv_h:
        Average PV production for each UTC hour of the day (W), len=24.
    params:
        Current MaestroParams (used as-is for all steps).
    now:
        Current UTC datetime.  Simulation starts at *now* rounded to 15 min.
    battery_capacity_kwh:
        Usable battery capacity in kWh.
    regelung_aktiv:
        Whether the Maestro rule engine is enabled.
    max_discharge_power:
        Maximum battery discharge power in W.  Defaults to ``params.inverter_power``.
    price_q:
        Optional 96-element list of buy prices (€/kWh) indexed by quarter slot
        (slot 0 = 00:00–00:14, slot 1 = 00:15–00:29, …, slot 95 = 23:45–23:59,
        all in UTC).  Used only for cost accounting; rule engine still uses
        tariff_class from MaestroParams tariff_slots as before.
        If None, ``params.fixed_buy_price`` is used for every quarter.
    """
    _STEP_MINUTES = 15
    _STEP_H = _STEP_MINUTES / 60.0  # 0.25 h per step
    if horizon_h not in (24, 48):
        horizon_h = 24
    _STEPS = horizon_h * 4  # quarters
    _have_day2 = (
        horizon_h == 48
        and pv_h_day2 is not None
        and consumption_h_day2 is not None
    )

    if battery_capacity_kwh <= 0:
        battery_capacity_kwh = 15.0
    capacity_wh = battery_capacity_kwh * 1000.0
    max_disch_w = max_discharge_power or params.inverter_power

    # Round to current 15-min quarter
    _tz = now.tzinfo or timezone.utc
    base = now.replace(second=0, microsecond=0, tzinfo=_tz)
    base = base.replace(minute=(base.minute // _STEP_MINUTES) * _STEP_MINUTES)

    # Fallback buy price per quarter when no price_q provided
    _fixed_buy = getattr(params, "fixed_buy_price", 0.30)
    _feed_in_price = getattr(params, "feed_in_price", 0.08)

    trajectory_soc: list[float] = []
    trajectory_hours: list[int] = []
    trajectory_phases: list[str] = []
    total_consumption_wh = 0.0
    grid_draw_wh = 0.0
    grid_feed_wh = 0.0
    pv_curtailed_wh = 0.0
    cost_eur = 0.0          # buy cost (€)
    revenue_eur = 0.0       # feed-in revenue (€)
    battery_throughput_wh = 0.0

    # Feed-in limit in W (inf = no limit configured)
    feed_in_limit_w = (
        params.feed_in_limit_percent / 100.0 * params.installed_kwp * 1000.0
        if params.feed_in_limit_percent > 0 and params.installed_kwp > 0
        else float("inf")
    )

    current_soc = float(soc)

    def _pv_lookup(arr: list[float], hour: int, minute: int) -> float:
        """Look up PV value at (hour, minute) for variable-resolution arrays.

        Supported lengths: 24 (hourly), 48 (30-min), 96 (15-min).
        Für 96/48 wird der Slot direkt indiziert (Solcast-Peaks bleiben
        erhalten). Für 24 (Hourly) wird **linear zwischen den
        Stunden-Samples interpoliert**, damit der Sub-Hour-Verlauf nicht
        als Stufenfunktion in den Forecast fällt (sonst entstehen
        sichtbare Mini-Treppen am Stundenwechsel).
        Energieerhaltung: Mittel über die 4 Quartale einer Stunde ≈
        arithmetisches Mittel der benachbarten Stunden-Samples.
        """
        n = len(arr)
        if n >= 96:
            return float(arr[hour * 4 + minute // 15])
        if n >= 48:
            return float(arr[hour * 2 + (1 if minute >= 30 else 0)])
        # 24 Stundenwerte → linear interpolieren.
        # arr[hour] = Mittelwert der Stunde, fixiert bei minute=30.
        a = float(arr[hour % 24])
        frac = (minute - 30) / 60.0
        if frac < 0:
            prev = float(arr[(hour - 1) % 24])
            return prev + (a - prev) * (frac + 1.0)
        b = float(arr[(hour + 1) % 24])
        return a + (b - a) * frac

    def _cons_lookup(arr: list[float], hour: int, minute: int) -> float:
        """Linear interpolation of hourly consumption between samples.

        Verbrauchs-Array hat 24 Stundenwerte. Ohne Interpolation ist
        ``cons_w`` innerhalb einer Stunde konstant → Slope-Sprung am
        Stundenwechsel. Mit Interpolation analog zu :func:`_pv_lookup`.
        """
        a = float(arr[hour % 24])
        frac = (minute - 30) / 60.0
        if frac < 0:
            prev = float(arr[(hour - 1) % 24])
            return prev + (a - prev) * (frac + 1.0)
        b = float(arr[(hour + 1) % 24])
        return a + (b - a) * frac

    for q in range(_STEPS):
        sim_now = base + timedelta(minutes=_STEP_MINUTES * (q + 1))
        # Lookup-Stunde für PV-/Verbrauchs-Profile: diese Arrays sind in
        # ConsumptionStats und _read_pv_forecast_profile nach UTC-Stunde
        # gebucketed. ``sim_now`` wird vom Coordinator mit ``dt_util.now()``
        # (lokal) erzeugt, daher ist ``sim_now.hour`` lokale Zeit. Ohne
        # Konvertierung greifen wir bei lokal 04:30 (Sommer) auf den
        # UTC-04-Slot = 06:00 lokal zu, was den Forecast vor Sonnenaufgang
        # fälschlich als „PV vorhanden" markiert.
        if sim_now.tzinfo is not None:
            sim_now_utc = sim_now.astimezone(timezone.utc)
        else:
            sim_now_utc = sim_now.replace(tzinfo=timezone.utc)
        lookup_hour = sim_now_utc.hour
        lookup_minute = sim_now_utc.minute
        # ``hour_idx`` (für Trajectory-Output und Quarter-Indizes) bleibt in
        # lokaler Zeit, damit price_q (lokale Tarifslots) und Trajektorie-
        # Beschriftung weiterhin stimmen.
        hour_idx = sim_now.hour

        # Day-1 vs day-2 lookup based on elapsed hours from base
        elapsed_h = (sim_now - base).total_seconds() / 3600.0
        if _have_day2 and elapsed_h >= 24.0:
            cons_arr = consumption_h_day2
            pv_arr = pv_h_day2
        else:
            cons_arr = consumption_h
            pv_arr = pv_h

        # Quarter-of-day index for price_q lookup (0–95, only valid in day 1)
        quarter_idx = hour_idx * 4 + sim_now.minute // _STEP_MINUTES

        cons_w = max(0.0, _cons_lookup(cons_arr, lookup_hour, lookup_minute))
        pv_w = max(0.0, _pv_lookup(pv_arr, lookup_hour, lookup_minute))

        # Approximate grid for state construction (grid balances the system)
        pv_surplus_w = pv_w - cons_w  # positive = export without battery

        state = MaestroState(
            soc=current_soc,
            pv_power=pv_w,
            house_power=cons_w,
            # Approximate: grid covers any deficit not yet compensated by battery
            grid_power=max(0.0, -pv_surplus_w),
            battery_power=0.0,
        )

        decision: MaestroDecision = decide(
            state, params, sim_now, regelung_aktiv=regelung_aktiv
        )
        phase = decision.phase

        # ── Determine battery net power for this step ───────────────────────
        # Discriminator ist primär der power_mode, NICHT charge_power_limit:
        # seit dem Spreading-/Idle-Fix liefert decide() bei „Ladung gesperrt,
        # Entladung frei" power_mode=NORMAL mit charge_power_limit=1 (1 W
        # Sentinel). Wenn man hier 1 W als „lade konstant" interpretiert,
        # wird der ganze Trace flach – obwohl der Akku nachts realistisch
        # entladen würde, um den Hausverbrauch zu decken.
        if decision.power_mode == POWER_MODE_DISCHARGE or phase == PHASE_MORNING_DISCHARGE:
            # Forced discharge: cover house consumption.
            bat_net_w = -min(max_disch_w, cons_w)
        elif decision.power_mode == POWER_MODE_IDLE:
            # Hard idle (z. B. HT-Schutz): kein Akku-Fluss.
            bat_net_w = 0.0
        elif decision.power_mode in (POWER_MODE_CHARGE, POWER_MODE_CHARGE_FROM_GRID) and (
            decision.charge_power_limit is not None and decision.charge_power_limit > 1
        ):
            # Echte Zwangsladung (Korridor, Spreading aktiv, Notfall, Curtailment).
            bat_net_w = min(decision.charge_power_limit, params.max_charge_power)
        else:
            # NORMAL (auch mit charge_power_limit=1 als „Laden gesperrt"-Sentinel):
            # passive PV-Pufferung + freies Entladen bei Defizit.
            charge_cap = params.max_charge_power
            if decision.charge_power_limit is not None:
                charge_cap = min(charge_cap, max(0, int(decision.charge_power_limit)))
            if pv_surplus_w > 0:
                bat_net_w = min(pv_surplus_w, charge_cap)
            else:
                bat_net_w = max(-max_disch_w, pv_surplus_w)

        # ── SoC update (15-min step = 0.25 h) ──────────────────────────────
        delta_wh = bat_net_w * _STEP_H
        raw_soc = current_soc + delta_wh / capacity_wh * 100.0
        # Clamp to [0, 100] and track rejected charge (battery full)
        if raw_soc > 100.0:
            rejected_wh = (raw_soc - 100.0) / 100.0 * capacity_wh
            bat_net_w -= rejected_wh / _STEP_H  # adjust power for grid accounting
            current_soc = 100.0
        elif raw_soc < 0.0:
            # Akku leer: die nicht aus dem Akku entnommene Energie muss
            # aus dem Netz kommen. Ohne diese Korrektur würde grid_draw_wh
            # auf 0 stehen, obwohl Hausverbrauch >0 ist (Self-Sufficiency
            # wäre fälschlich 100%).
            deficit_wh = (0.0 - raw_soc) / 100.0 * capacity_wh
            bat_net_w += deficit_wh / _STEP_H  # bat_net_w war negativ → wird Richtung 0 korrigiert
            current_soc = 0.0
        else:
            current_soc = raw_soc

        battery_throughput_wh += abs(bat_net_w) * _STEP_H

        # ── Grid accounting with curtailment ────────────────────────────────
        # grid_net > 0 = feed-in, grid_net < 0 = draw
        grid_net_w = pv_w - cons_w - bat_net_w
        step_kwh = abs(grid_net_w) * _STEP_H / 1000.0
        if grid_net_w < 0:
            grid_draw_wh += abs(grid_net_w) * _STEP_H
            # Cost accounting: use quarter price if available
            buy_price = (
                price_q[quarter_idx]
                if price_q and 0 <= quarter_idx < len(price_q)
                else _fixed_buy
            )
            cost_eur += step_kwh * buy_price
        else:
            # Anything above the feed-in limit is curtailed (physically lost)
            if grid_net_w > feed_in_limit_w:
                pv_curtailed_wh += (grid_net_w - feed_in_limit_w) * _STEP_H
                grid_feed_wh += feed_in_limit_w * _STEP_H
                revenue_eur += (feed_in_limit_w * _STEP_H / 1000.0) * _feed_in_price
            else:
                grid_feed_wh += grid_net_w * _STEP_H
                revenue_eur += step_kwh * _feed_in_price

        total_consumption_wh += cons_w * _STEP_H

        trajectory_soc.append(round(current_soc, 1))
        trajectory_hours.append(hour_idx)
        trajectory_phases.append(phase)

    min_soc = min(trajectory_soc) if trajectory_soc else current_soc
    max_soc = max(trajectory_soc) if trajectory_soc else current_soc

    self_sufficiency: float | None = None
    if total_consumption_wh > 0:
        covered_wh = total_consumption_wh - grid_draw_wh
        self_sufficiency = round(max(0.0, min(1.0, covered_wh / total_consumption_wh)), 3)

    return ForecastResult(
        trajectory_soc=trajectory_soc,
        trajectory_hours=trajectory_hours,
        trajectory_phases=trajectory_phases,
        min_soc=round(min_soc, 1),
        max_soc=round(max_soc, 1),
        grid_draw_kwh=round(grid_draw_wh / 1000.0, 3),
        grid_feed_in_kwh=round(grid_feed_wh / 1000.0, 3),
        pv_curtailed_kwh=round(pv_curtailed_wh / 1000.0, 3),
        self_sufficiency=self_sufficiency,
        cost_eur=round(cost_eur, 4),
        revenue_eur=round(revenue_eur, 4),
        battery_throughput_kwh=round(battery_throughput_wh / 1000.0, 3),
    )
