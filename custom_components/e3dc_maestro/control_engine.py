"""Pure rule engine for E3DC Maestro – no I/O, fully unit-testable.

Seasonal calculations use daylight-length-based interpolation derived from
the Spencer/Cooper astronomical sunrise/sunset formulas (location-aware,
latitude-dependent). No fixed day-of-year constants.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Tariff slot scheduler (Phase C)
# ──────────────────────────────────────────────────────────────────────────────

# Tariff classes used by the scheduler.
TARIFF_HIGH = "high"
TARIFF_LOW = "low"
TARIFF_NORMAL = "normal"


@dataclass
class TariffSlot:
    """A recurring tariff window pinned to a set of weekdays."""

    weekdays: frozenset[int]   # 0=Mon … 6=Sun
    start_h: float             # fractional hour of day [0, 24)
    end_h: float               # fractional hour of day, may be < start_h to span midnight
    class_: str = TARIFF_HIGH  # "high" | "low" | "normal"
    min_reserve_soc: float | None = None  # optional explicit reserve floor for this slot


@dataclass
class TariffSchedule:
    """Collection of tariff slots plus an optional dynamic-price source."""

    slots: list[TariffSlot] = field(default_factory=list)
    dynamic_source_entity: str | None = None
    cheap_threshold: float | None = None  # €/kWh – price <= threshold ⇒ "low"


def _slot_active(slot: TariffSlot, weekday: int, hour: float) -> bool:
    """True if the slot covers (weekday, fractional hour-of-day)."""
    if slot.start_h <= slot.end_h:
        # Same-day slot.
        if weekday not in slot.weekdays:
            return False
        return slot.start_h <= hour < slot.end_h
    # Wrap-around slot, e.g. 22 → 06: night portion belongs to the previous day.
    if weekday in slot.weekdays and hour >= slot.start_h:
        return True
    prev_day = (weekday - 1) % 7
    if prev_day in slot.weekdays and hour < slot.end_h:
        return True
    return False


def current_tariff_class(
    now: datetime,
    schedule: TariffSchedule,
    current_price: float | None = None,
) -> str:
    """Resolve the active tariff class for ``now``.

    Resolution order:
      1. Any matching slot of class "high" wins.
      2. Otherwise dynamic price ≤ cheap_threshold ⇒ "low".
      3. Otherwise any matching slot of class "low" ⇒ "low".
      4. Fallback: "normal".
    """
    weekday = now.weekday()
    hour = now.hour + now.minute / 60.0

    matched: set[str] = set()
    for slot in schedule.slots:
        if _slot_active(slot, weekday, hour):
            matched.add(slot.class_)

    if TARIFF_HIGH in matched:
        return TARIFF_HIGH
    if (
        schedule.cheap_threshold is not None
        and current_price is not None
        and current_price <= schedule.cheap_threshold
    ):
        return TARIFF_LOW
    if TARIFF_LOW in matched:
        return TARIFF_LOW
    return TARIFF_NORMAL


def active_tariff_slot(now: datetime, schedule: TariffSchedule) -> TariffSlot | None:
    """Return the highest-priority active slot (high > low > normal) or None."""
    weekday = now.weekday()
    hour = now.hour + now.minute / 60.0
    priority = {TARIFF_HIGH: 0, TARIFF_LOW: 1, TARIFF_NORMAL: 2}
    best: TariffSlot | None = None
    for slot in schedule.slots:
        if not _slot_active(slot, weekday, hour):
            continue
        if best is None or priority.get(slot.class_, 99) < priority.get(best.class_, 99):
            best = slot
    return best


def tariff_schedule_from_params(params: "MaestroParams") -> TariffSchedule:
    """Derive a TariffSchedule from the legacy ``ht_*`` + cheap-threshold params.

    This keeps the user-facing config (single HT window Mo–Fr plus optional
    Sat/Sun toggles, cheap threshold for dynamic tariffs) compatible while the
    engine internally operates on the generic slot model.
    """
    if params.tariff_schedule is not None:
        return params.tariff_schedule

    slots: list[TariffSlot] = []
    if params.ht_enabled:
        weekdays: set[int] = {0, 1, 2, 3, 4}
        if params.ht_sat:
            weekdays.add(5)
        if params.ht_sun:
            weekdays.add(6)
        slots.append(
            TariffSlot(
                weekdays=frozenset(weekdays),
                start_h=float(params.ht_on),
                end_h=float(params.ht_off),
                class_=TARIFF_HIGH,
            )
        )
    threshold = (
        params.cheap_threshold
        if params.dynamic_tariff_enabled
        else None
    )
    return TariffSchedule(slots=slots, cheap_threshold=threshold)


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MaestroState:
    """Current measured values, read from HA sensor entities."""
    soc: float               # % 0-100
    pv_power: float          # W, positive = generating
    house_power: float       # W, positive = consuming
    grid_power: float        # W, positive = feed-in to grid
    battery_power: float     # W, positive = charging
    pv_forecast_remaining_kwh: float | None = None  # remaining PV today (kWh)
    # EVCC state (D1)
    evcc_charging: bool = False          # True when EV is actively charging
    evcc_mode: str | None = None         # EVCC charging mode: "now", "pv", "minpv", …
    # Phase D: rolling consumption statistics from HA Recorder
    consumption_avg_w_24h: float | None = None        # rolling 24h average house power (W)
    consumption_avg_w_ht_window: float | None = None  # rolling average house power (W) in HT-slot hours
    consumption_data_days: int = 0                    # how many days of stats are available
    # F1+: Forward-Looking (vorausschauende Ladung)
    tomorrow_pv_kwh: float | None = None              # morgen erwarteter PV-Ertrag (kWh)
    tomorrow_consumption_kwh: float | None = None     # morgen erwarteter Verbrauch (kWh, wochentagspezifisch)


@dataclass
class MaestroParams:
    """Configuration parameters (from config entry options)."""
    # System
    inverter_power: float = 12000
    max_charge_power: float = 3000
    min_charge_power: float = 300
    installed_kwp: float = 10.0
    feed_in_limit_percent: float = 70.0
    advanced_corridor: bool = False
    lower_corridor: float = 500
    upper_corridor: float = 1500
    # Season
    charge_threshold: float = 15
    charge_target: float = 85
    winter_minimum_hour: float = 11
    summer_maximum_hour: float = 14
    summer_charge_end: float = 18.5
    # HT
    ht_enabled: bool = False
    ht_on: float = 5
    ht_off: float = 21
    ht_min: float = 50
    ht_sockel: float = 10
    ht_sat: bool = True
    ht_sun: bool = True
    # Dynamic tariff
    dynamic_tariff_enabled: bool = False
    cheap_threshold: float = 0.10
    max_grid_charge_kwh: float = 3.0
    # Phase C: explicit tariff slot schedule (optional override).
    # If None, a schedule is derived from the legacy ht_*/cheap_threshold fields.
    tariff_schedule: TariffSchedule | None = None
    # PV forecast (charge delay)
    pv_forecast_enabled: bool = False
    pv_forecast_threshold_kwh: float = 5.0
    battery_capacity_kwh: float = 10.0
    pv_forecast_safety_factor: float = 1.2
    # Wallbox
    wallbox_enabled: bool = False
    wallbox_min_current: float = 6
    wallbox_max_current: float = 16
    wallbox_phases: int = 3
    wallbox_min_surplus: float = 1400
    # Heat pump
    hp_enabled: bool = False
    hp_min_surplus: float = 2000
    hp_max_price: float = 0.15
    hp_min_run_minutes: int = 20
    hp_min_pause_minutes: int = 15
    # Failsafe
    watchdog_timeout: int = 10
    # A1: SoC hysteresis (applied in coordinator before calling decide)
    soc_hysteresis_percent: float = 2.0
    # A2: Charge-power ramp (applied in coordinator after calling decide)
    charge_ramp_w_per_cycle: int = 200
    # B1: Seasonal emergency reserve
    seasonal_reserve_enabled: bool = False
    reserve_winter_percent: float = 30
    reserve_equinox_percent: float = 15
    # Phase D: consumption-adaptive reserves (override static seasonal/HT-min when
    # enough recorder history is available). Default off → legacy behaviour.
    adaptive_reserve_enabled: bool = False
    adaptive_reserve_lookback_days: int = 14   # how many days of stats to query
    adaptive_reserve_min_days: int = 7         # require ≥ N days of data, else fall back
    adaptive_reserve_safety_factor: float = 1.3  # multiplier on rolling average kWh need
    adaptive_reserve_min_soc: float = 5.0      # never recommend below this floor (%)
    adaptive_reserve_max_soc: float = 90.0     # cap recommendation at this ceiling (%)
    # D1: EVCC integration
    evcc_enabled: bool = False
    evcc_now_value: str = "now"  # State-Wert der den 'Sofortladen'-Modus signalisiert
    evcc_discharge_limit_w: float = 0  # max Entladeleistung bei EVCC Now-Modus (W, 0 = vollständig sperren)
    # E2: Prognosebasiertes Spreading (Ladeverteilung)
    spreading_enabled: bool = False
    spreading_target_soc: float = 100.0  # Ziel-SoC für die Ladeverteilung (Standard: 100 %)
    # E3/Phase 1: Curtailment Guard
    curtailment_guard_enabled: bool = True
    curtailment_activation_w: float = 1500  # W – Hysterese-Einschaltschwelle
    curtailment_release_w: float = 500      # W – Hysterese-Ausschaltschwelle
    # Phase 2: Untere-Korridor-Pause
    lower_corridor_pause_enabled: bool = True
    # Phase 4: Two-Tier Ladeende
    two_tier_enabled: bool = False
    charge_target_late: float = 95.0      # % SoC – spätes Ziel nach charge_end_h (z.B. 95 %)
    late_charge_end_h: float = 20.0       # Stunde bis zu der Nachladung möglich (z.B. 20:00)
    # Phase 6: Morning Pre-Discharge
    morning_discharge_mode: str = "off"   # off | passive | active_house | active_grid
    morning_unload_soc: float = 40.0      # % SoC Entlade-Ziel
    morning_unload_start_soc: float = 60.0  # % SoC Einschalt-Schwelle
    pre_discharge_offset_h: float = 4.0  # h vor Ladeende-Start
    pre_discharge_max_power_w: float = 2000  # W max. Entladeleistung
    pre_discharge_safety_factor: float = 1.3  # Prognose-Sicherheitsfaktor
    pre_discharge_tibber_auto: bool = False   # Tibber-gesteuerte Auto-Hochstufung
    morning_grid_export_threshold: float = 0.15  # €/kWh – Preis für active_grid-Hochstufung
    # Phase 7: Astro-Modus
    astro_enabled: bool = False
    astro_latitude: float = 48.0         # Breitengrad (Dezimalgrad)
    astro_longitude: float = 11.0        # Längengrad (Dezimalgrad)
    charge_end_sunset_offset_h: float = -2.0   # h relativ zu Sonnenuntergang (negativ = vorher)
    charge_start_sunrise_offset_h: float = 2.0  # h nach Sonnenaufgang
    # F0: Flat-Curve / Morning-Cap + Gentle-Charge
    morning_cap_enabled: bool = False
    morning_cap_soc: float = 30.0       # % SoC ceiling until morning_cap_until_h
    morning_cap_until_h: float = 9.0    # h local time: cap is active before this hour
    # Mindest-SoC, der vor pv_delay/astro_wait erreicht werden muss
    # (0 = Floor deaktiviert, Standardverhalten).
    delay_min_soc: float = 0.0
    gentle_charge_enabled: bool = False
    gentle_charge_factor: float = 0.35  # scale charge power (not during guard/emergency)
    # G0: Hard SoC Limit (Akku-Schonung) – aktiver Lade-Stop oberhalb des Deckels.
    # Curtailment Guard bleibt funktional (überschreibt den Deckel, damit
    # sonst abgeregelte PV-Leistung weiter in den Akku gepuffert werden kann).
    hard_soc_limit_enabled: bool = False
    hard_soc_limit: float = 80.0        # % SoC – harter Maximalwert
    # F1+: Forward-Looking (vorausschauende Ladung)
    forward_looking_enabled: bool = False
    forward_looking_max_soc: float = 100.0
    # F3: Auto-Optimierungs-Modus
    auto_mode_enabled: bool = False
    auto_mode_objective: str = "self_consumption"  # self_consumption | cost | co2
    # Manuelle Erzwingung der Akku-Entladung (Dashboard-Schalter)
    force_discharge_power_w: float = 3000.0


@dataclass
class MaestroDecision:
    """What the rule engine decided to do this tick."""
    phase: str                              # see const.ALL_PHASES
    reason: str                             # human-readable explanation
    # Battery / power limits
    charge_power_limit: float | None = None  # W  (None = clear limits)
    discharge_power_limit: float | None = None
    power_mode: str | None = None           # see POWER_MODE_* constants
    manual_charge_kwh: float | None = None  # only set if manual charge needed
    # Wallbox
    wallbox_current: float | None = None
    wallbox_off: bool = False
    # Heat pump
    hp_on: bool | None = None               # None = no change
    # Monitoring helpers
    target_soc: float | None = None         # calculated target SoC for this time
    target_charge_power: float | None = None
    feed_in_excess_w: float | None = None   # W above feed-in limit when PHASE_FEED_IN_LIMIT


# ──────────────────────────────────────────────────────────────────────────────
# Seasonal math (daylight-length-based, location-aware)
# ──────────────────────────────────────────────────────────────────────────────

def _day_of_year(dt: datetime) -> int:
    return dt.timetuple().tm_yday


def daylight_factor(dt: datetime, params: MaestroParams) -> float:
    """Return a seasonal factor in [0.0, 1.0] based on actual daylight length.

    0.0 = winter solstice (shortest day), 1.0 = summer solstice (longest day).
    Uses the Spencer/Cooper astronomical model via astro_sunrise_sunset(), so
    the result is location-aware (depends on params.astro_latitude).
    Clamped to [0, 1] to handle edge cases near polar latitudes.
    """
    sunrise_h, sunset_h = astro_sunrise_sunset(dt, params)
    daylight = sunset_h - sunrise_h

    # Reference daytimes at solstices (same year and timezone as dt)
    dt_winter = dt.replace(month=12, day=21, hour=12, minute=0, second=0, microsecond=0)
    dt_summer = dt.replace(month=6, day=21, hour=12, minute=0, second=0, microsecond=0)

    sr_w, ss_w = astro_sunrise_sunset(dt_winter, params)
    l_min = ss_w - sr_w

    sr_s, ss_s = astro_sunrise_sunset(dt_summer, params)
    l_max = ss_s - sr_s

    if l_max <= l_min:
        return 0.5  # degenerate: equatorial or polar

    return max(0.0, min(1.0, (daylight - l_min) / (l_max - l_min)))


def seasonal_charge_end_hour(dt: datetime, params: MaestroParams) -> float:
    """Return the charge-end hour for today based on season.

    If astro_enabled: sunset + charge_end_sunset_offset_h (real astronomy).
    Otherwise: daylight-length-based linear interpolation between
    winter_minimum_hour (shortest day) and summer_charge_end (longest day).
    """
    if params.astro_enabled:
        _, sunset_h = astro_sunrise_sunset(dt, params)
        return sunset_h + params.charge_end_sunset_offset_h

    factor = daylight_factor(dt, params)
    return params.winter_minimum_hour + (params.summer_charge_end - params.winter_minimum_hour) * factor


def ht_min_dynamic(dt: datetime, params: MaestroParams) -> float:
    """Daylight-length-based HT minimum SoC reserve.

    At winter solstice (factor=0) → ht_min (e.g. 50 %)
    At summer solstice (factor=1) → ht_sockel (e.g. 10 %)
    """
    factor = daylight_factor(dt, params)
    return params.ht_min + (params.ht_sockel - params.ht_min) * factor


def target_soc_for_time(dt: datetime, params: MaestroParams) -> float:
    """Return the SoC target that should be reached by charge-end time today.

    Phase 4 – Two-Tier:
    - Before charge_end_h:  linear ramp from morning_anchor to charge_target
    - charge_end_h – late_charge_end_h: linear ramp charge_target → charge_target_late
    - After late_charge_end_h:  hold charge_target_late
    """
    charge_end_h = seasonal_charge_end_hour(dt, params)
    hour_now = dt.hour + dt.minute / 60

    # Two-Tier late window
    if params.two_tier_enabled and hour_now >= charge_end_h:
        late_end = params.late_charge_end_h
        if hour_now >= late_end:
            return params.charge_target_late
        window = max(late_end - charge_end_h, 0.001)
        fraction = (hour_now - charge_end_h) / window
        return params.charge_target + (params.charge_target_late - params.charge_target) * fraction

    # Before or at charge-end: standard linear ramp
    if hour_now >= charge_end_h:
        return params.charge_target
    morning_anchor = max(20.0, params.charge_threshold)
    morning_hour = 6.0
    if hour_now <= morning_hour:
        return morning_anchor
    fraction = (hour_now - morning_hour) / max(charge_end_h - morning_hour, 1)
    return morning_anchor + (params.charge_target - morning_anchor) * fraction


def seasonal_reserve_soc(dt: datetime, params: MaestroParams) -> float:
    """Daylight-length-based seasonal emergency reserve SoC (%).

    At winter solstice (factor=0) → reserve_winter_percent (e.g. 30 %)
    At summer solstice (factor=1) → reserve_equinox_percent (e.g. 15 %)
    """
    factor = daylight_factor(dt, params)
    return params.reserve_winter_percent + (params.reserve_equinox_percent - params.reserve_winter_percent) * factor


def _slot_duration_hours(slot: TariffSlot) -> float:
    """Return slot length in hours, handling midnight wrap."""
    if slot.start_h <= slot.end_h:
        return max(0.0, slot.end_h - slot.start_h)
    return max(0.0, 24.0 - slot.start_h + slot.end_h)


def _adaptive_data_sufficient(state: MaestroState, params: MaestroParams) -> bool:
    """True when enough recorder history is available for adaptive reserves."""
    if not params.adaptive_reserve_enabled:
        return False
    return state.consumption_data_days >= params.adaptive_reserve_min_days


def adaptive_emergency_reserve_soc(
    state: MaestroState, params: MaestroParams
) -> float | None:
    """Consumption-adaptive emergency reserve (%) based on rolling 24h house load.

    Returns ``None`` if adaptive mode is off or not enough data. Otherwise
    computes:

        needed_kWh = avg_w_24h / 1000 * 24 * safety_factor
        reserve_%  = needed_kWh / battery_capacity_kWh * 100

    Clamped to ``[adaptive_reserve_min_soc, adaptive_reserve_max_soc]``.
    """
    if not _adaptive_data_sufficient(state, params):
        return None
    if state.consumption_avg_w_24h is None or state.consumption_avg_w_24h <= 0:
        return None
    if params.battery_capacity_kwh <= 0:
        return None
    needed_kwh = (
        state.consumption_avg_w_24h / 1000.0 * 24.0
        * params.adaptive_reserve_safety_factor
    )
    reserve_pct = needed_kwh / params.battery_capacity_kwh * 100.0
    return max(
        params.adaptive_reserve_min_soc,
        min(params.adaptive_reserve_max_soc, reserve_pct),
    )


def adaptive_ht_reserve_soc(
    state: MaestroState,
    params: MaestroParams,
    slot: TariffSlot | None,
) -> float | None:
    """Consumption-adaptive HT reserve (%) based on rolling load in HT window.

    Returns ``None`` when adaptive mode is off, no HT slot is active, or
    insufficient data. Otherwise:

        needed_kWh = avg_w_ht_window / 1000 * slot_duration_h * safety_factor
        reserve_%  = needed_kWh / battery_capacity_kWh * 100
    """
    if slot is None:
        return None
    if not _adaptive_data_sufficient(state, params):
        return None
    if state.consumption_avg_w_ht_window is None or state.consumption_avg_w_ht_window <= 0:
        return None
    if params.battery_capacity_kwh <= 0:
        return None
    duration_h = _slot_duration_hours(slot)
    if duration_h <= 0:
        return None
    needed_kwh = (
        state.consumption_avg_w_ht_window / 1000.0 * duration_h
        * params.adaptive_reserve_safety_factor
    )
    reserve_pct = needed_kwh / params.battery_capacity_kwh * 100.0
    return max(
        params.adaptive_reserve_min_soc,
        min(params.adaptive_reserve_max_soc, reserve_pct),
    )


def forward_looking_charge_target(
    state: MaestroState,
    params: MaestroParams,
    base_target: float,
) -> float:
    """Compute a forward-looking charge target (%).

    Idee: Wenn morgen wenig PV erwartet wird und der Verbrauch nicht aus PV
    gedeckt werden kann, wird das heutige Ladeziel angehoben, sodass
    PV-Überschuss heute in den Akku statt ins Netz fließt.

    Inputs:
      * state.tomorrow_pv_kwh           – morgen erwarteter PV-Ertrag (kWh)
      * state.tomorrow_consumption_kwh  – morgen erwarteter Verbrauch (kWh,
        wochentagspezifisch wenn vorhanden, sonst 24h-Mittel)
      * params.battery_capacity_kwh

    Rückgabe:
      * base_target wenn Feature aus oder Daten fehlen
      * sonst clamped(base_target + extra%, [base_target, cap])
        cap = min(forward_looking_max_soc, hard_soc_limit?)

    Hard-SoC-Limit hat Vorrang (Akku-Schonung > Smart-Charge).
    """
    if not params.forward_looking_enabled:
        return base_target
    if state.tomorrow_pv_kwh is None or state.tomorrow_consumption_kwh is None:
        return base_target
    if params.battery_capacity_kwh <= 0:
        return base_target

    deficit_kwh = max(0.0, state.tomorrow_consumption_kwh - state.tomorrow_pv_kwh)
    if deficit_kwh <= 0:
        return base_target

    extra_pct = deficit_kwh / params.battery_capacity_kwh * 100.0

    cap = params.forward_looking_max_soc
    if params.hard_soc_limit_enabled:
        cap = min(cap, params.hard_soc_limit)
    cap = min(cap, 100.0)

    return max(base_target, min(base_target + extra_pct, cap))


def time_to_target_power(state: MaestroState, params: MaestroParams, now: datetime, target: float) -> float:
    """Calculate desired charge power (W) from remaining energy and remaining time.

    Physical formula::

        needed_kWh  = (target - soc) / 100 * battery_capacity_kwh
        hours_left  = max(0.1, charge_end_h - hour_now)
        P           = needed_kWh * 1000 / hours_left

    Clamped to [min_charge_power, max_charge_power].
    Returns 0.0 when target ≤ soc (nothing to charge).
    """
    needed_kwh = (target - state.soc) / 100.0 * params.battery_capacity_kwh
    if needed_kwh <= 0:
        return 0.0
    charge_end_h = seasonal_charge_end_hour(now, params)
    hour_now = now.hour + now.minute / 60.0
    hours_left = max(0.1, charge_end_h - hour_now)
    raw_w = needed_kwh * 1000.0 / hours_left
    return max(params.min_charge_power, min(params.max_charge_power, raw_w))


def desired_charge_power(soc: float, target: float, params: MaestroParams, now: datetime | None = None) -> float:
    """Calculate desired charge power (W) for the corridor phase.

    advanced_corridor mode: SoC-delta mapped linearly to [lower_corridor, upper_corridor].
    Default mode: time-to-target (physical energy / remaining hours).
    """
    soc_delta = target - soc
    if params.advanced_corridor:
        if soc_delta > 0:
            raw = params.lower_corridor + (soc_delta / 100) * (params.upper_corridor - params.lower_corridor)
        else:
            raw = 0.0
        return max(params.min_charge_power, min(params.max_charge_power, raw)) if raw > 0 else 0.0

    # Time-to-target strategy (default)
    if now is None or soc_delta <= 0:
        return 0.0
    # Reconstruct a minimal MaestroState for time_to_target_power
    _state = MaestroState(
        soc=soc, pv_power=0, house_power=0, grid_power=0, battery_power=0
    )
    return time_to_target_power(_state, params, now, target)


def _is_ht_window(dt: datetime, params: MaestroParams) -> bool:
    """Return True if now is within a tariff slot of class "high".

    Thin wrapper around :func:`current_tariff_class` for backward
    compatibility with code/tests that referenced the legacy helper.
    """
    schedule = tariff_schedule_from_params(params)
    return current_tariff_class(dt, schedule) == TARIFF_HIGH


def _feed_in_limit_w(params: MaestroParams) -> float:
    """Absolute feed-in limit in Watts."""
    return params.feed_in_limit_percent / 100 * params.installed_kwp * 1000


def _curtailment_floor_w(state: MaestroState, params: MaestroParams) -> float:
    """Minimum charge power to prevent curtailment this tick (Watts).

    Two floors, take the maximum:
    1. Feed-in floor: excess above the grid export limit
    2. Inverter-clipping floor: DC surplus exceeding AC inverter rating
    """
    feed_in_limit = _feed_in_limit_w(params)
    floor_feed_in = max(0.0, state.pv_power - state.house_power - feed_in_limit)
    floor_inverter = max(0.0, state.pv_power - params.inverter_power)
    return max(floor_feed_in, floor_inverter)


# SoC ceiling above which any charge command is futile (battery saturated).
# Used to suppress charging in feed-in / curtailment / spreading branches when
# the battery cannot accept further energy.
BATTERY_FULL_SOC_CEILING = 98.0


def _apply_house_ceiling(
    charge_power: float,
    state: MaestroState,
    params: MaestroParams,
    phase: str,
    current_price: float | None,
    *,
    tariff_class: str | None = None,
) -> float:
    """Cap charge power to available PV surplus to avoid drawing from grid.

    Bypassed for phases that intentionally use grid power:
    - EMERGENCY, FEED_IN_LIMIT, CURTAILMENT_GUARD
    - active tariff class is "low" (cheap dynamic tariff)
    """
    from .const import PHASE_CURTAILMENT_GUARD, PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT
    bypass_phases = {PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT, PHASE_CURTAILMENT_GUARD}
    if phase in bypass_phases:
        return charge_power
    if tariff_class == TARIFF_LOW:
        return charge_power
    surplus = max(0.0, state.pv_power - state.house_power)
    return min(charge_power, surplus) if surplus > 0 else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Phase 7: Astronomical sunrise/sunset calculation
# ──────────────────────────────────────────────────────────────────────────────

def astro_sunrise_sunset(dt: datetime, params: MaestroParams) -> tuple[float, float]:
    """Return (sunrise_h, sunset_h) in local time (same TZ as dt).

    Uses Spencer/Cooper solar geometry formulas with standard -0.833°
    horizon correction (refraction + solar disk). Accurate to ~2 min.

    Returns (0.0, 24.0) for polar day and (12.0, 12.0) for polar night.
    """
    doy = dt.timetuple().tm_yday
    lat_rad = math.radians(params.astro_latitude)

    # Day angle (radians)
    B = 2.0 * math.pi * (doy - 1) / 365.0

    # Solar declination (Spencer, radians)
    decl = (
        0.006918
        - 0.399912 * math.cos(B) + 0.070257 * math.sin(B)
        - 0.006758 * math.cos(2 * B) + 0.000907 * math.sin(2 * B)
        - 0.002697 * math.cos(3 * B) + 0.001480 * math.sin(3 * B)
    )

    # Equation of time (Spencer, minutes)
    EoT = 229.18 * (
        0.000075
        + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
        - 0.014615 * math.cos(2 * B) - 0.040890 * math.sin(2 * B)
    )

    # Standard atmosphere correction: -0.833° (refraction + solar disk)
    h_corr = math.radians(-0.833)
    cos_omega = (
        math.sin(h_corr) - math.sin(lat_rad) * math.sin(decl)
    ) / (math.cos(lat_rad) * math.cos(decl))

    if cos_omega <= -1.0:
        return 0.0, 24.0   # polar day
    if cos_omega >= 1.0:
        return 12.0, 12.0  # polar night

    omega = math.acos(cos_omega)
    half_day_h = math.degrees(omega) / 15.0

    # UTC offset of dt (0 for naive datetimes)
    utc_offset_h = (
        dt.utcoffset().total_seconds() / 3600.0
        if dt.utcoffset() is not None else 0.0
    )

    # Solar noon in local time
    solar_noon_local = (
        12.0
        - params.astro_longitude / 15.0
        + utc_offset_h
        - EoT / 60.0
    )

    return solar_noon_local - half_day_h, solar_noon_local + half_day_h


# ──────────────────────────────────────────────────────────────────────────────
# Phase 6: Morning Pre-Discharge helper
# ──────────────────────────────────────────────────────────────────────────────

def _morning_discharge_decision(
    state: MaestroState,
    params: MaestroParams,
    now: datetime,
    target: float,
    current_price: float | None,
) -> "MaestroDecision | None":
    """Return a PHASE_MORNING_DISCHARGE decision if conditions are met, else None.

    Activation requires ALL of:
    1. mode != "off"
    2. soc >= morning_unload_start_soc  (high enough to bother)
    3. soc >  morning_unload_soc        (still above target floor)
    4. now < charge_end_h - pre_discharge_offset_h  (enough time before charging starts)
    5. PV forecast gating: pv_forecast_remaining_kwh >= needed * safety_factor
    """
    from .const import (
        MORNING_DISCHARGE_ACTIVE_GRID,
        MORNING_DISCHARGE_ACTIVE_HOUSE,
        MORNING_DISCHARGE_OFF,
        MORNING_DISCHARGE_PASSIVE,
        PHASE_MORNING_DISCHARGE,
        POWER_MODE_DISCHARGE,
        POWER_MODE_IDLE,
        POWER_MODE_NORMAL,
    )

    mode = params.morning_discharge_mode
    if mode == MORNING_DISCHARGE_OFF:
        return None

    # Tibber-Auto-Override: upgrade or downgrade mode based on price
    if params.pre_discharge_tibber_auto and params.dynamic_tariff_enabled and current_price is not None:
        if current_price > params.morning_grid_export_threshold:
            mode = MORNING_DISCHARGE_ACTIVE_GRID
        elif current_price <= params.cheap_threshold and mode == MORNING_DISCHARGE_ACTIVE_GRID:
            mode = MORNING_DISCHARGE_ACTIVE_HOUSE  # downgrade if buying is cheap

    # Condition 2: SoC high enough to warrant unloading
    if state.soc < params.morning_unload_start_soc:
        return None
    # Condition 3: Still above the unload target floor
    if state.soc <= params.morning_unload_soc:
        return None

    # Condition 4: Time window – must be before (charge_end_h - offset)
    charge_end_h = seasonal_charge_end_hour(now, params)
    charge_begin_h = charge_end_h - params.pre_discharge_offset_h
    hour_now = now.hour + now.minute / 60
    if hour_now >= charge_begin_h:
        return None

    # Condition 5: PV forecast gating
    if params.pv_forecast_enabled and state.pv_forecast_remaining_kwh is not None:
        needed_kwh = (
            (params.charge_target - params.morning_unload_soc) / 100.0
            * params.battery_capacity_kwh
        )
        min_forecast = needed_kwh * params.pre_discharge_safety_factor
        if state.pv_forecast_remaining_kwh < min_forecast:
            return None  # Not enough sun expected – skip pre-discharge

    # Calculate discharge rate
    delta_soc = state.soc - params.morning_unload_soc
    delta_kwh = delta_soc / 100.0 * params.battery_capacity_kwh
    remaining_h = max(0.001, charge_begin_h - hour_now)
    rate_w = delta_kwh * 1000.0 / remaining_h
    if mode == MORNING_DISCHARGE_ACTIVE_GRID:
        rate_w = max(rate_w, params.pre_discharge_max_power_w)
    rate_w = min(rate_w, params.pre_discharge_max_power_w)
    rate_w = max(100.0, rate_w)  # minimum meaningful discharge

    if mode == MORNING_DISCHARGE_PASSIVE:
        # Only block charging – let house load drain the battery naturally
        return MaestroDecision(
            phase=PHASE_MORNING_DISCHARGE,
            reason=(
                f"Vorentladung passiv: SoC {state.soc:.0f}% → {params.morning_unload_soc:.0f}% "
                f"(Ladestart {charge_begin_h:.1f} Uhr)"
            ),
            power_mode=POWER_MODE_IDLE,
            charge_power_limit=0.0,
            target_soc=target,
        )
    else:
        # active_house or active_grid: actively discharge
        return MaestroDecision(
            phase=PHASE_MORNING_DISCHARGE,
            reason=(
                f"Vorentladung {mode}: {delta_kwh:.2f} kWh in {remaining_h:.1f} h "
                f"→ {rate_w:.0f} W (SoC {state.soc:.0f}% → {params.morning_unload_soc:.0f}%)"
            ),
            power_mode=POWER_MODE_DISCHARGE,
            charge_power_limit=None,
            discharge_power_limit=rate_w,
            target_soc=target,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main decision function
# ──────────────────────────────────────────────────────────────────────────────

def decide(
    state: MaestroState,
    params: MaestroParams,
    now: datetime,
    *,
    regelung_aktiv: bool = True,
    curtailment_guard_active: bool = False,
    current_price: float | None = None,
    grid_charged_today_kwh: float = 0.0,
    hp_running: bool = False,
    hp_last_change_minutes: float = 999,
    force_discharge: bool = False,
) -> MaestroDecision:
    """Determine the desired action for this control cycle.

    Priority (highest first):
      1. Regelung off → clear everything, return PHASE_OFF
      2. Emergency charge (SoC < charge_threshold)
      3. Feed-in limit exceeded
      4. Seasonal reserve protection (SoC ≤ seasonal reserve, B1)
      5. EVCC Now-mode pause (D1)
      6. HT protection (peak tariff window + SoC above ht_min_dynamic)
      6.5 Morning Pre-Discharge
      6.75 Astro-Wait (sunrise gate: don't charge before sunrise + offset)
      7. Seasonal corridor
      8. Idle

    Wallbox and heat pump decisions are appended independently.
    """
    from .const import (
        PHASE_CORRIDOR,
        PHASE_CURTAILMENT_GUARD,
        PHASE_EMERGENCY,
        PHASE_EVCC_PAUSE,
        PHASE_FEED_IN_LIMIT,
        PHASE_FORCE_DISCHARGE,
        PHASE_HT_PROTECTION,
        PHASE_IDLE,
        PHASE_MORNING_DISCHARGE,
        PHASE_MORNING_CAP,
        PHASE_HARD_SOC_LIMIT,
    PHASE_ASTRO_WAIT,
        PHASE_OFF,
        PHASE_PV_DELAY,
        PHASE_RESERVE_PROTECTION,
        PHASE_SPREADING,
        POWER_MODE_CHARGE,
        POWER_MODE_DISCHARGE,
        POWER_MODE_IDLE,
        POWER_MODE_NORMAL,
    )

    target = target_soc_for_time(now, params)

    # Resolve active tariff class once (Phase C).
    schedule = tariff_schedule_from_params(params)
    tariff_class = current_tariff_class(now, schedule, current_price)
    active_slot = active_tariff_slot(now, schedule)

    # ── 1. Master switch off ────────────────────────────────────────────────
    if not regelung_aktiv:
        return MaestroDecision(
            phase=PHASE_OFF,
            reason="Regelung deaktiviert",
            charge_power_limit=None,
            discharge_power_limit=None,
            power_mode=POWER_MODE_NORMAL,
            target_soc=target,
        )

    # ── 1.5 Manuelle Entladung (Dashboard-Schalter) ─────────────────────────
    # Höchste Priorität nach dem Master-Switch: erzwingt aktive Entladung des
    # Akkus bis zur Notstromreserve / Ladeschwelle.
    if force_discharge:
        floor_soc = float(params.charge_threshold)
        if params.seasonal_reserve_enabled:
            floor_soc = max(floor_soc, seasonal_reserve_soc(now, params))
        if state.soc > floor_soc:
            rate_w = max(100.0, min(params.force_discharge_power_w, params.max_charge_power))
            return MaestroDecision(
                phase=PHASE_FORCE_DISCHARGE,
                reason=(
                    f"Manuelle Entladung erzwungen: SoC {state.soc:.0f}\u202f% → "
                    f"Floor {floor_soc:.0f}\u202f%, {rate_w:.0f}\u202fW"
                ),
                power_mode=POWER_MODE_DISCHARGE,
                charge_power_limit=None,
                discharge_power_limit=rate_w,
                target_soc=target,
            )
        return MaestroDecision(
            phase=PHASE_FORCE_DISCHARGE,
            reason=(
                f"Manuelle Entladung: SoC {state.soc:.0f}\u202f% ≤ Floor "
                f"{floor_soc:.0f}\u202f% → Pause"
            ),
            power_mode=POWER_MODE_IDLE,
            target_soc=target,
        )

    feed_in_limit = _feed_in_limit_w(params)

    # ── 2. Emergency charge ─────────────────────────────────────────────────
    if state.soc < params.charge_threshold:
        return MaestroDecision(
            phase=PHASE_EMERGENCY,
            reason=f"SoC {state.soc:.0f}% unter Ladeschwelle {params.charge_threshold:.0f}%",
            power_mode=POWER_MODE_CHARGE,
            charge_power_limit=params.max_charge_power,
            target_soc=target,
            target_charge_power=params.max_charge_power,
        )

    # ── 3. Feed-in limit ────────────────────────────────────────────────────
    if state.grid_power > feed_in_limit:
        # Akku-voll-Schutz: bei (nahezu) vollem Akku kann eine zusätzliche
        # Ladeanforderung den Überschuss nicht aufnehmen → Wechselrichter
        # regelt PV von selbst ab. Statt einen wirkungslosen Ladebefehl zu
        # senden, geben wir IDLE zurück und lassen die Limits frei.
        if state.soc >= BATTERY_FULL_SOC_CEILING:
            return MaestroDecision(
                phase=PHASE_IDLE,
                reason=(
                    f"Einspeisung {state.grid_power:.0f}W > Limit {feed_in_limit:.0f}W, "
                    f"aber SoC {state.soc:.0f}% ≥ {BATTERY_FULL_SOC_CEILING:.0f}% – "
                    "Akku voll, keine zusätzliche Ladeanforderung"
                ),
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=None,
                target_soc=target,
            )
        excess = state.grid_power - feed_in_limit
        boost = min(state.battery_power + excess, params.max_charge_power)
        return MaestroDecision(
            phase=PHASE_FEED_IN_LIMIT,
            reason=(
                f"Einspeisung {state.grid_power:.0f}W > Limit {feed_in_limit:.0f}W, "
                f"Ladeleistung auf {boost:.0f}W erhöht"
            ),
            power_mode=POWER_MODE_CHARGE,
            charge_power_limit=boost,
            target_soc=target,
            target_charge_power=boost,
            feed_in_excess_w=excess,
        )

    # ── 4. Seasonal reserve protection (B1) ───────────────────────────────────────────────
    if params.seasonal_reserve_enabled:
        adaptive_pct = adaptive_emergency_reserve_soc(state, params)
        reserve_soc = adaptive_pct if adaptive_pct is not None else seasonal_reserve_soc(now, params)
        if state.soc <= reserve_soc:
            source = "verbrauchsadaptiv" if adaptive_pct is not None else "saisonal"
            return MaestroDecision(
                phase=PHASE_RESERVE_PROTECTION,
                reason=(
                    f"Notstromreserve {reserve_soc:.0f}% ({source}) ≥ SoC {state.soc:.0f}% – "
                    f"Entladung gesperrt"
                ),
                power_mode=POWER_MODE_IDLE,
                target_soc=target,
            )

    # ── 5. EVCC Now-mode pause (D1) ───────────────────────────────────────────────────────
    if params.evcc_enabled and state.evcc_charging and state.evcc_mode == params.evcc_now_value:
        limit_w = params.evcc_discharge_limit_w
        if limit_w <= 0:
            # Entladung vollständig sperren
            return MaestroDecision(
                phase=PHASE_EVCC_PAUSE,
                reason=f"EVCC lädt im Now-Modus ({params.evcc_now_value!r}) – Entladung gesperrt",
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=None,
                discharge_power_limit=0.0,
                target_soc=target,
            )
        else:
            # Entladung auf Grundlastwert begrenzen
            return MaestroDecision(
                phase=PHASE_EVCC_PAUSE,
                reason=f"EVCC lädt im Now-Modus ({params.evcc_now_value!r}) – Entladung auf {limit_w:.0f} W begrenzt",
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=None,
                discharge_power_limit=limit_w,
                target_soc=target,
            )

    # ── 6. HT protection ─────────────────────────────────────────────────────────────────────
    if tariff_class == TARIFF_HIGH:
        slot_floor = active_slot.min_reserve_soc if active_slot else None
        adaptive_floor = adaptive_ht_reserve_soc(state, params, active_slot)
        if slot_floor is not None:
            ht_min = slot_floor
            ht_min_source = "Slot-Override"
        elif adaptive_floor is not None:
            ht_min = adaptive_floor
            ht_min_source = "verbrauchsadaptiv"
        else:
            ht_min = ht_min_dynamic(now, params)
            ht_min_source = "saisonal"
        if state.soc > ht_min:
            slot_start = active_slot.start_h if active_slot else 0.0
            slot_end = active_slot.end_h if active_slot else 24.0
            return MaestroDecision(
                phase=PHASE_HT_PROTECTION,
                reason=(
                    f"Hochtarif-Slot ({slot_start:.0f}–{slot_end:.0f} Uhr), "
                    f"SoC {state.soc:.0f}% > HT-Reserve {ht_min:.0f}% ({ht_min_source})"
                ),
                power_mode=POWER_MODE_IDLE,
                target_soc=target,
            )
    # ── 6.5 Morning Pre-Discharge ──────────────────────────────────────────────────────
    _md_decision = _morning_discharge_decision(
        state, params, now, target, current_price
    )
    if _md_decision is not None:
        return _md_decision

    # ── 6.7 Morning-Cap: block charging until cap_until_h (must run BEFORE astro_wait) ─
    # Morning-Cap is a hard SoC ceiling — it overrides astro_wait, otherwise astro_wait
    # would hand control back to E3DC and the device would charge to 100% on its own,
    # ignoring the cap. Convention: POWER_MODE_NORMAL + charge_power_limit=1 W blocks
    # charging while leaving discharge free, so the battery still covers the house load.
    if params.morning_cap_enabled and not curtailment_guard_active:
        hour_now = now.hour + now.minute / 60
        if hour_now < params.morning_cap_until_h and state.soc >= params.morning_cap_soc:
            return MaestroDecision(
                phase=PHASE_MORNING_CAP,
                reason=(
                    f"Morning-Cap: SoC {state.soc:.0f}% ≥ Cap {params.morning_cap_soc:.0f}% "
                    f"(aktiv bis {params.morning_cap_until_h:.1f} Uhr lokal, "
                    f"jetzt {hour_now:.1f} Uhr)"
                ),
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=1,  # 1 W = effektiv keine Ladung, Entladen frei
                target_soc=target,
            )

    # ── 6.75 Astro-Wait: Ladestart-Sperre bis Sonnenaufgang + Offset ────────────────
    # NORMAL + 1 W: blockt Laden, lässt Entladung zur Hausabdeckung zu (sonst würde
    # der Akku nachts unnötig auf 100 % bleiben oder gar Netzbezug verursachen).
    if params.astro_enabled and state.soc < params.charge_target:
        sunrise_h, _ = astro_sunrise_sunset(now, params)
        charge_start_gate_h = sunrise_h + params.charge_start_sunrise_offset_h
        hour_now = now.hour + now.minute / 60
        # delay_min_soc: Floor unterhalb dem astro_wait nicht blockieren darf.
        if hour_now < charge_start_gate_h and state.soc >= params.delay_min_soc:
            return MaestroDecision(
                phase=PHASE_ASTRO_WAIT,
                reason=(
                    f"Astro-Modus: Ladestart ab {charge_start_gate_h:.1f} Uhr "
                    f"(Sonnenaufgang {sunrise_h:.1f} Uhr + {params.charge_start_sunrise_offset_h:.1f} h), "
                    f"SoC {state.soc:.0f}%"
                ),
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=1,  # 1 W = effektiv keine Ladung, Entladen frei
                target_soc=target,
            )

    # ── 6.9 Hard SoC Limit (G0): aktiver Lade-Stop oberhalb des Deckels ─────────────
    # Sobald SoC ≥ hard_soc_limit greift ein 1 W-Lade-Limit (Entladung bleibt
    # frei). Der Curtailment Guard ist absichtlich ausgenommen, damit sonst
    # abgeregelte PV-Leistung weiter in den Akku gepuffert werden kann.
    if (
        params.hard_soc_limit_enabled
        and not curtailment_guard_active
        and state.soc >= params.hard_soc_limit
    ):
        return MaestroDecision(
            phase=PHASE_HARD_SOC_LIMIT,
            reason=(
                f"Hard-SoC-Limit: SoC {state.soc:.0f}\u202f% \u2265 Deckel "
                f"{params.hard_soc_limit:.0f}\u202f% \u2013 Ladung blockiert, "
                "Entladen frei (Abregelschutz bleibt aktiv)"
            ),
            power_mode=POWER_MODE_NORMAL,
            charge_power_limit=1,  # 1 W = effektiv keine Ladung
            target_soc=target,
        )

    charge_power = desired_charge_power(state.soc, target, params, now)
    if charge_power > 0 and state.soc < params.charge_target:
        # 7a. PV forecast → delay charging if enough sun expected today
        # Aber NICHT bei aktivem Abregelschutz: dort muss Ladung als Senke
        # für überschüssige PV einspringen, sonst wird Strom abgeregelt.
        if (
            params.pv_forecast_enabled
            and state.pv_forecast_remaining_kwh is not None
            and not curtailment_guard_active
        ):
            required_kwh = max(
                0.0,
                (target - state.soc) / 100.0 * params.battery_capacity_kwh,
            )
            min_required = max(
                params.pv_forecast_threshold_kwh,
                required_kwh * params.pv_forecast_safety_factor,
            )
            charge_end_h = seasonal_charge_end_hour(now, params)
            hour_now = now.hour + now.minute / 60
            # only delay before charge-end time → otherwise we'd never fill
            # delay_min_soc: SoC-Floor – darunter darf pv_delay nicht blockieren,
            # damit der Korridor erst die Mindestreserve auflädt.
            if (
                state.pv_forecast_remaining_kwh >= min_required
                and hour_now < charge_end_h
                and state.soc >= params.delay_min_soc
            ):
                floor_note = (
                    f", Floor {params.delay_min_soc:.0f}%"
                    if params.delay_min_soc > 0
                    else ""
                )
                return MaestroDecision(
                    phase=PHASE_PV_DELAY,
                    reason=(
                        f"PV-Prognose {state.pv_forecast_remaining_kwh:.1f} kWh "
                        f"≥ benötigt {min_required:.1f} kWh → Ladung verzögert "
                        f"(SoC {state.soc:.0f}% → Ziel {target:.0f}%{floor_note})"
                    ),
                    power_mode=POWER_MODE_NORMAL,
                    charge_power_limit=None,
                    target_soc=target,
                )
        # 7b. Lower-corridor pause: if charge power too low and no curtailment → idle
        if (
            params.lower_corridor_pause_enabled
            and charge_power < params.lower_corridor
            and not curtailment_guard_active
        ):
            return MaestroDecision(
                phase=PHASE_IDLE,
                reason=(
                    f"Korridor-Pause: Soll-Ladeleistung {charge_power:.0f} W "
                    f"< unterer Korridor {params.lower_corridor:.0f} W"
                ),
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=None,
                target_soc=target,
            )
        effective_charge = _apply_house_ceiling(
            charge_power, state, params, PHASE_CORRIDOR, current_price,
            tariff_class=tariff_class,
        )
        return MaestroDecision(
            phase=PHASE_CORRIDOR,
            reason=(
                f"Ladekorridor: SoC {state.soc:.0f}% → Ziel {target:.0f}%, "
                f"Leistung {effective_charge:.0f}W"
            ),
            power_mode=POWER_MODE_NORMAL,
            charge_power_limit=effective_charge if effective_charge > 0 else None,
            target_soc=target,
            target_charge_power=effective_charge,
        )

    # ── 8. Spreading: limit charge rate to spread remaining capacity to charge-end ──
    # Phase 4 Two-Tier: use charge_target_late as upper goal when in late window
    _spread_upper_soc = (
        params.charge_target_late
        if params.two_tier_enabled
        else params.spreading_target_soc
    )
    # Akku-voll-Schutz: oberhalb der Sättigungsschwelle gibt es nichts mehr zu
    # verteilen – jegliche zusätzliche Ladeleistung wäre wirkungslos.
    if state.soc >= BATTERY_FULL_SOC_CEILING:
        _spread_active = False
    else:
        _spread_active = params.spreading_enabled and state.soc < _spread_upper_soc
    if _spread_active:
        charge_end_h = seasonal_charge_end_hour(now, params)
        hour_now = now.hour + now.minute / 60
        # Determine the end of the spreading window
        _spread_end_h = (
            params.late_charge_end_h
            if params.two_tier_enabled and hour_now >= charge_end_h
            else charge_end_h
        )
        # Hinweis: Früher gab es hier ein PV-Forecast-Gate, das Spreading
        # an sonnigen Tagen komplett übersprungen hat (return PV_DELAY mit
        # charge_power_limit=None → clear_power_limits → Akku lädt mit
        # voller PV-Überschussleistung). Das widerspricht aber dem Ziel
        # von Spreading („Akku gleichmäßig bis charge_end füllen, damit
        # PV-Überschuss tagsüber ins Netz gehen kann"). Die Spreading-Rate
        # selbst (remaining_kwh / remaining_hours) limitiert die Ladung
        # bereits sanft – ein zusätzliches Skip ist nicht nötig.
        if hour_now < _spread_end_h:
            remaining_hours = _spread_end_h - hour_now
            remaining_soc = _spread_upper_soc - state.soc
            remaining_kwh = remaining_soc / 100.0 * params.battery_capacity_kwh
            if remaining_hours > 0:
                spreading_rate_w = remaining_kwh * 1000.0 / remaining_hours
                spreading_rate_w = max(
                    params.min_charge_power,
                    min(params.max_charge_power, spreading_rate_w),
                )
                # House-ceiling: don't draw from grid unless bypass condition
                spreading_rate_w = _apply_house_ceiling(
                    spreading_rate_w, state, params, PHASE_SPREADING, current_price,
                    tariff_class=tariff_class,
                )
                if spreading_rate_w < params.min_charge_power:
                    return MaestroDecision(
                        phase=PHASE_IDLE,
                        reason=(
                            f"Spreading-Pause: PV-Überschuss "
                            f"{max(0.0, state.pv_power - state.house_power):.0f}\u202fW "
                            f"< Min-Ladeleistung {params.min_charge_power:.0f}\u202fW"
                        ),
                        power_mode=POWER_MODE_NORMAL,
                        charge_power_limit=None,
                        target_soc=target,
                    )
                return MaestroDecision(
                    phase=PHASE_SPREADING,
                    reason=(
                        f"Ladeverteilung: {remaining_kwh:.1f}\u202fkWh in "
                        f"{remaining_hours:.1f}\u202fh \u2192 {spreading_rate_w:.0f}\u202fW "
                        f"(SoC {state.soc:.0f}\u202f% \u2192 {_spread_upper_soc:.0f}\u202f% "
                        f"bis {_spread_end_h:.1f}\u202fUhr)"
                    ),
                    power_mode=POWER_MODE_NORMAL,
                    charge_power_limit=spreading_rate_w,
                    target_soc=target,
                    target_charge_power=spreading_rate_w,
                )

    # ── 8b. Spreading-Ziel erreicht: Ladung aktiv blockieren ────────────────
    # Wenn der SoC das Spreading-Ziel überschritten hat (z.B. User reduziert
    # spreading_target_soc von 100 % auf 90 %, aktueller SoC 95 %), würde
    # die Engine sonst auf Section 10 IDLE fallen → clear_power_limits →
    # Wechselrichter lädt mit vollem PV-Überschuss bis 100 %. Stattdessen
    # setzen wir hier ein hartes Mini-Limit, damit Überschuss ins Netz fließt.
    if (
        params.spreading_enabled
        and state.soc >= _spread_upper_soc
        and state.soc < BATTERY_FULL_SOC_CEILING
        and not curtailment_guard_active
    ):
        return MaestroDecision(
            phase=PHASE_IDLE,
            reason=(
                f"Spreading-Ziel erreicht: SoC {state.soc:.0f}\u202f% \u2265 "
                f"{_spread_upper_soc:.0f}\u202f% \u2013 Ladung blockiert, "
                "\u00dcberschuss \u2192 Netz"
            ),
            power_mode=POWER_MODE_NORMAL,
            charge_power_limit=1,  # 1 W = effektiv keine Ladung
            target_soc=target,
        )

    # ── 9. Curtailment Guard (idle would win – curtailment may still be active) ──
    if params.curtailment_guard_enabled and curtailment_guard_active:        # Akku-voll-Schutz: gleicher Grund wie in Feed-in-Limit. Wenn der Akku
        # gesättigt ist, kann ein Ladebefehl die Abregelung nicht verhindern;
        # wir lassen den Wechselrichter regulär abregeln.
        if state.soc >= BATTERY_FULL_SOC_CEILING:
            return MaestroDecision(
                phase=PHASE_IDLE,
                reason=(
                    f"Abregelschutz unterdrückt: SoC {state.soc:.0f}% ≥ "
                    f"{BATTERY_FULL_SOC_CEILING:.0f}% – Akku voll, keine Ladeanforderung"
                ),
                power_mode=POWER_MODE_NORMAL,
                charge_power_limit=None,
                target_soc=target,
            )
        floor_w = _curtailment_floor_w(state, params)
        if floor_w > 0:
            guard_power = min(floor_w, params.max_charge_power)
            return MaestroDecision(
                phase=PHASE_CURTAILMENT_GUARD,
                reason=(
                    f"Abregelschutz: PV {state.pv_power:.0f}W, "
                    f"Haus {state.house_power:.0f}W, "
                    f"Limit {_feed_in_limit_w(params):.0f}W → "
                    f"Mindest-Ladeleistung {guard_power:.0f}W"
                ),
                power_mode=POWER_MODE_CHARGE,
                charge_power_limit=guard_power,
                target_soc=target,
                target_charge_power=guard_power,
            )

    # ── 10. Idle ─────────────────────────────────────────────────────────────
    # SoC am oder über dem Ziel und keine andere Phase aktiv: Ladung hart
    # blockieren (sonst würde clear_power_limits den Eigenverbrauchs-Default
    # auslösen → Akku füllt sich mit vollem PV-Überschuss bis 100 %).
    # power_mode=NORMAL mit charge_power_limit=1 W deckelt nur das Laden;
    # Entladen bleibt vollständig erlaubt, damit plötzliche Lastspitzen
    # weiterhin aus dem Akku gedeckt werden statt Netzbezug zu erzeugen.
    # Nur Section 9 (Abregelschutz) darf vorher noch laden, falls die
    # Einspeisegrenze überschritten würde – und dann auch nur den Überschuss.
    return MaestroDecision(
        phase=PHASE_IDLE,
        reason=(
            f"SoC {state.soc:.0f}% ≥ Ziel {target:.0f}%, kein Handlungsbedarf "
            "(Ladung blockiert, Entladen frei)"
        ),
        power_mode=POWER_MODE_NORMAL,
        charge_power_limit=1,  # 1 W = effektiv keine Ladung, Entladen unberührt
        target_soc=target,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Wallbox surplus calculation
# ──────────────────────────────────────────────────────────────────────────────

def wallbox_desired_current(
    state: MaestroState,
    params: MaestroParams,
    current_wallbox_current: float = 0,
) -> tuple[float | None, bool]:
    """Return (desired_current_A, turn_off).

    Surplus = PV - house - battery_charge.
    If surplus >= wallbox_min_surplus → compute current and clamp.
    If surplus < min_current threshold → turn off.
    """
    if not params.wallbox_enabled:
        return None, False

    surplus = state.pv_power - state.house_power - max(state.battery_power, 0)
    voltage = 230.0
    phases = float(params.wallbox_phases)
    desired = surplus / (voltage * phases)
    desired = max(params.wallbox_min_current, min(params.wallbox_max_current, desired))

    if surplus < params.wallbox_min_surplus:
        return None, True  # below threshold → off

    return desired, False


# ──────────────────────────────────────────────────────────────────────────────
# Heat pump decision
# ──────────────────────────────────────────────────────────────────────────────

def hp_desired_state(
    state: MaestroState,
    params: MaestroParams,
    now: datetime,
    current_price: float | None,
    hp_running: bool,
    hp_last_change_minutes: float,
) -> bool | None:
    """Return True/False to switch HP, or None for no change."""
    if not params.hp_enabled:
        return None

    now_time = now.time()
    start = time.fromisoformat(params.__dict__.get("hp_time_start", "06:00"))
    end = time.fromisoformat(params.__dict__.get("hp_time_end", "22:00"))
    in_window = start <= now_time <= end

    surplus = state.pv_power - state.house_power
    cheap = current_price is not None and current_price <= params.hp_max_price
    want_on = in_window and (surplus >= params.hp_min_surplus or cheap)

    if want_on and not hp_running:
        if hp_last_change_minutes >= params.hp_min_pause_minutes:
            return True
    elif not want_on and hp_running:
        if hp_last_change_minutes >= params.hp_min_run_minutes:
            return False
    return None
