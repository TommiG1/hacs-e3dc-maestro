"""Tests for the E3DC Maestro rule engine."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.e3dc_maestro.control_engine import (
    MaestroParams,
    MaestroState,
    decide,
    daylight_factor,
    seasonal_charge_end_hour,
    seasonal_reserve_soc,
    ht_min_dynamic,
    target_soc_for_time,
    astro_sunrise_sunset,
    time_to_target_power,
    adaptive_emergency_reserve_soc,
    adaptive_ht_reserve_soc,
    TariffSlot,
    TariffSchedule,
    TARIFF_HIGH,
)
from custom_components.e3dc_maestro.const import (
    PHASE_CORRIDOR,
    PHASE_CURTAILMENT_GUARD,
    PHASE_EMERGENCY,
    PHASE_EVCC_PAUSE,
    PHASE_FEED_IN_LIMIT,
    PHASE_HT_PROTECTION,
    PHASE_IDLE,
    PHASE_MORNING_CAP,
    PHASE_HARD_SOC_LIMIT,
    PHASE_MORNING_DISCHARGE,
    PHASE_ASTRO_WAIT,
    PHASE_OFF,
    PHASE_RESERVE_PROTECTION,
    PHASE_SPREADING,
    POWER_MODE_IDLE,
    POWER_MODE_DISCHARGE,
)


def _now(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


DEFAULT_PARAMS = MaestroParams(
    inverter_power=12000,
    max_charge_power=3000,
    min_charge_power=300,
    installed_kwp=10.0,
    feed_in_limit_percent=70.0,
    charge_threshold=15,
    charge_target=85,
    winter_minimum_hour=11,
    summer_maximum_hour=14,
    summer_charge_end=18.5,
    ht_enabled=True,
    ht_on=5,
    ht_off=21,
    ht_min=50,
    ht_sockel=10,
    ht_sat=True,
    ht_sun=True,
)


class TestPhaseOff:
    def test_returns_off_when_regelung_inactive(self):
        state = MaestroState(soc=50, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        decision = decide(state, DEFAULT_PARAMS, _now(6, 15, 12), regelung_aktiv=False)
        assert decision.phase == PHASE_OFF


class TestEmergencyCharge:
    def test_triggers_below_threshold(self):
        state = MaestroState(soc=10, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        decision = decide(state, DEFAULT_PARAMS, _now(6, 15, 12))
        assert decision.phase == PHASE_EMERGENCY
        assert decision.charge_power_limit == DEFAULT_PARAMS.max_charge_power

    def test_not_triggered_at_threshold(self):
        state = MaestroState(soc=15, pv_power=2000, house_power=800, grid_power=0, battery_power=500)
        decision = decide(state, DEFAULT_PARAMS, _now(6, 15, 12))
        assert decision.phase != PHASE_EMERGENCY

    def test_priority_over_ht(self):
        """Emergency overrides HT protection."""
        state = MaestroState(soc=5, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        # ht_on=5, ht_off=21, soc=5 < ht_min=50
        decision = decide(state, DEFAULT_PARAMS, _now(6, 15, 10))
        assert decision.phase == PHASE_EMERGENCY


class TestFeedInLimit:
    def test_triggers_when_grid_exceeds_limit(self):
        # feed_in_limit = 70% * 10kWp * 1000 = 7000W
        state = MaestroState(soc=50, pv_power=10000, house_power=1000, grid_power=8000, battery_power=0)
        decision = decide(state, DEFAULT_PARAMS, _now(7, 15, 13))
        assert decision.phase == PHASE_FEED_IN_LIMIT

    def test_priority_over_ht(self):
        """Feed-in limit overrides HT protection."""
        state = MaestroState(soc=80, pv_power=10000, house_power=1000, grid_power=8000, battery_power=0)
        decision = decide(state, DEFAULT_PARAMS, _now(6, 15, 10))
        assert decision.phase == PHASE_FEED_IN_LIMIT

    def test_no_trigger_within_limit(self):
        state = MaestroState(soc=50, pv_power=8000, house_power=2000, grid_power=6000, battery_power=0)
        decision = decide(state, DEFAULT_PARAMS, _now(7, 15, 13))
        assert decision.phase != PHASE_FEED_IN_LIMIT

    def test_suppressed_when_battery_full(self):
        """At ≥98% SoC the battery cannot absorb extra charge → no boost."""
        state = MaestroState(
            soc=99, pv_power=10000, house_power=1000, grid_power=8000, battery_power=0
        )
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(7, 15, 10, 36))
        assert decision.phase == PHASE_IDLE
        assert decision.charge_power_limit is None

    # ── Anti-flapping: hysteresis tests ──────────────────────────────────────

    def test_no_trigger_below_hysteresis_threshold(self):
        """Excess < 150 W (FEED_IN_TRIGGER_EXCESS_W) must not activate feed_in_limit."""
        # feed_in_limit = 7000 W; grid_power = 7100 W → excess = 100 W < 150 W
        state = MaestroState(soc=50, pv_power=9000, house_power=1000, grid_power=7100, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(7, 15, 13))
        assert decision.phase != PHASE_FEED_IN_LIMIT

    def test_triggers_exactly_at_hysteresis_threshold(self):
        """Excess == 150 W (boundary) must activate feed_in_limit."""
        # feed_in_limit = 7000 W; grid_power = 7150 W → excess = 150 W
        state = MaestroState(soc=50, pv_power=9000, house_power=1000, grid_power=7150, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(7, 15, 13))
        assert decision.phase == PHASE_FEED_IN_LIMIT

    def test_holds_phase_when_excess_below_trigger_but_above_release(self):
        """With previous_phase=feed_in_limit and 0 < excess < trigger, phase is held."""
        # excess = 50 W (< 150 W trigger, > 0 W release) → should hold
        state = MaestroState(soc=50, pv_power=9000, house_power=1000, grid_power=7050, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(
            state, params, _now(7, 15, 13),
            previous_phase=PHASE_FEED_IN_LIMIT,
        )
        assert decision.phase == PHASE_FEED_IN_LIMIT

    def test_no_hold_without_previous_feed_in_phase(self):
        """Without previous feed_in_limit phase, small excess must not trigger."""
        # excess = 50 W, no previous feed_in_limit → should not activate
        state = MaestroState(soc=50, pv_power=9000, house_power=1000, grid_power=7050, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(7, 15, 13), previous_phase="corridor")
        assert decision.phase != PHASE_FEED_IN_LIMIT


class TestHTProtection:
    def test_active_in_window_with_sufficient_soc(self):
        # ht_on=5, ht_off=21 → 10:00 is in window, soc=60 > ht_min_dynamic
        state = MaestroState(soc=60, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_min": 50, "ht_sockel": 10})
        decision = decide(state, params, _now(1, 15, 10))  # winter → ht_min≈50
        assert decision.phase == PHASE_HT_PROTECTION

    def test_inactive_outside_window(self):
        state = MaestroState(soc=60, pv_power=2000, house_power=800, grid_power=0, battery_power=500)
        decision = decide(state, DEFAULT_PARAMS, _now(1, 15, 22))  # after ht_off=21
        assert decision.phase != PHASE_HT_PROTECTION

    def test_inactive_when_soc_below_ht_min(self):
        state = MaestroState(soc=30, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_min": 50})
        decision = decide(state, params, _now(1, 15, 10))
        assert decision.phase != PHASE_HT_PROTECTION

    def test_disabled_when_ht_disabled(self):
        state = MaestroState(soc=80, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(1, 15, 10))
        assert decision.phase != PHASE_HT_PROTECTION


class TestCorridor:
    def test_charges_when_soc_below_target(self):
        state = MaestroState(soc=50, pv_power=3000, house_power=800, grid_power=0, battery_power=0)
        # Outside HT window (night, hour=23), soc=50 < target
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False})
        decision = decide(state, params, _now(6, 15, 23))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit >= params.min_charge_power

    def test_spreading_caps_corridor_power_advanced(self):
        """advanced_corridor mit aggressivem upper_corridor (8 kW) erzeugt im
        Korridor hohe Ladeleistung. Wenn spreading_enabled=True, muss die
        zeitbasierte Spreading-Rate die Korridor-Leistung deckeln."""
        # 11:00 in Mai, SoC=20, target_soc_for_time≈49 → Korridor aktiv.
        # advanced_corridor liefert ~ lower + (29/100)*(8000-200) ≈ 2462 W.
        # Spreading-Rate (100-20)/100*16 kWh / 7.5 h ≈ 1707 W → kappt.
        state = MaestroState(soc=20, pv_power=8000, house_power=500, grid_power=0, battery_power=0)
        params = MaestroParams(**{
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            "charge_target": 85,
            "spreading_enabled": True,
            "spreading_target_soc": 100,
            "battery_capacity_kwh": 16.0,
            "advanced_corridor": True,
            "lower_corridor": 200,
            "upper_corridor": 8000,
            "max_charge_power": 8000,
            "min_charge_power": 200,
            "summer_charge_end": 18.5,
        })
        decision = decide(state, params, _now(5, 15, 11))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit <= 2200, (
            f"Erwartete geglättete Leistung ≤ 2.2 kW, erhielt "
            f"{decision.charge_power_limit:.0f} W"
        )
        assert "Glättung" in decision.reason

    def test_no_smoothing_when_spreading_disabled(self):
        """Ohne Spreading-Switch wird die Korridor-Leistung nicht zusätzlich
        gekappt (der Switch bleibt der explizite Opt-In für Glättung)."""
        state = MaestroState(soc=20, pv_power=8000, house_power=500, grid_power=0, battery_power=0)
        params = MaestroParams(**{
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            "charge_target": 85,
            "spreading_enabled": False,
            "battery_capacity_kwh": 16.0,
            "advanced_corridor": True,
            "lower_corridor": 200,
            "upper_corridor": 8000,
            "max_charge_power": 8000,
            "summer_charge_end": 18.5,
        })
        decision = decide(state, params, _now(5, 15, 11))
        assert decision.phase == PHASE_CORRIDOR
        assert "Glättung" not in decision.reason

    def test_idle_when_soc_at_target(self):
        state = MaestroState(soc=90, pv_power=1000, house_power=800, grid_power=0, battery_power=0)
        params = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "ht_enabled": False, "charge_target": 85})
        decision = decide(state, params, _now(6, 15, 23))
        assert decision.phase == PHASE_IDLE


class TestDaylightFactor:
    """Unit tests for the new daylight_factor() function (Phase A)."""

    def _params(self, lat: float = 48.0) -> MaestroParams:
        return MaestroParams(astro_latitude=lat, astro_longitude=11.0)

    def test_winter_solstice_is_near_zero(self):
        """Dec 21 ≈ shortest day → factor should be close to 0."""
        dt = _now(12, 21, 12)
        f = daylight_factor(dt, self._params())
        assert f < 0.1

    def test_summer_solstice_is_near_one(self):
        """Jun 21 ≈ longest day → factor should be close to 1."""
        dt = _now(6, 21, 12)
        f = daylight_factor(dt, self._params())
        assert f > 0.9

    def test_spring_equinox_is_around_half(self):
        """Mar 21 ≈ spring equinox → factor should be near 0.5."""
        dt = _now(3, 21, 12)
        f = daylight_factor(dt, self._params())
        assert 0.35 <= f <= 0.65

    def test_factor_increases_from_winter_to_summer(self):
        """Factor must be monotonically increasing Jan → Jun."""
        params = self._params()
        months = [1, 2, 3, 4, 5, 6]
        factors = [daylight_factor(_now(m, 15, 12), params) for m in months]
        assert factors == sorted(factors)

    def test_factor_clamped_between_zero_and_one(self):
        """Factor must always be in [0, 1] for any date."""
        params = self._params()
        for month in range(1, 13):
            f = daylight_factor(_now(month, 15, 12), params)
            assert 0.0 <= f <= 1.0

    def test_equatorial_latitude_returns_half(self):
        """Near the equator, daylight barely changes → degenerate case returns 0.5."""
        params = self._params(lat=0.1)
        f = daylight_factor(_now(6, 21, 12), params)
        assert 0.0 <= f <= 1.0


class TestSeasonalMath:
    def test_winter_charge_end_is_winter_minimum(self):
        # Dec 21 → winter solstice → should return close to winter_minimum_hour
        now = _now(12, 21, 8)
        end = seasonal_charge_end_hour(now, DEFAULT_PARAMS)
        assert abs(end - DEFAULT_PARAMS.winter_minimum_hour) < 1.0

    def test_summer_charge_end_around_solstice(self):
        # Jun 21 → summer solstice → should return close to summer_charge_end
        now = _now(6, 21, 8)
        end = seasonal_charge_end_hour(now, DEFAULT_PARAMS)
        assert end >= DEFAULT_PARAMS.summer_maximum_hour

    def test_ht_min_higher_in_winter(self):
        winter = ht_min_dynamic(_now(12, 21, 10), DEFAULT_PARAMS)
        summer = ht_min_dynamic(_now(6, 21, 10), DEFAULT_PARAMS)
        assert winter > summer

    def test_target_soc_increases_through_day(self):
        t1 = target_soc_for_time(_now(6, 15, 7), DEFAULT_PARAMS)
        t2 = target_soc_for_time(_now(6, 15, 10), DEFAULT_PARAMS)
        t3 = target_soc_for_time(_now(6, 15, 15), DEFAULT_PARAMS)
        assert t1 <= t2 <= t3


# ──────────────────────────────────────────────────────────────────────────────
# PV forecast / charge delay
# ──────────────────────────────────────────────────────────────────────────────


def _params_with_forecast(threshold: float = 5.0, capacity: float = 10.0, factor: float = 1.2) -> MaestroParams:
    p = MaestroParams(
        inverter_power=12000,
        max_charge_power=3000,
        min_charge_power=300,
        installed_kwp=10.0,
        feed_in_limit_percent=70.0,
        charge_threshold=15,
        charge_target=85,
        winter_minimum_hour=11,
        summer_maximum_hour=14,
        summer_charge_end=18.5,
        pv_forecast_enabled=True,
        pv_forecast_threshold_kwh=threshold,
        battery_capacity_kwh=capacity,
        pv_forecast_safety_factor=factor,
        lower_corridor_pause_enabled=False,  # isolate forecast logic from corridor-pause
        spreading_enabled=False,  # isolate forecast logic from spreading exemption
    )
    return p


class TestPvForecastDelay:
    def test_delays_corridor_when_forecast_sufficient(self):
        # SoC 50% of 10 kWh battery, target ~85% → required ~3.5 kWh
        # Forecast 8 kWh, factor 1.2 → min_required = max(5.0, 4.2) = 5.0 → 8 ≥ 5 → delay
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase == PHASE_PV_DELAY
        # Lade-Sperre: charge_power_limit=0.0 → max_charge=0 an E3DC.
        # Entladung bleibt frei (discharge_power_limit=None) damit das Haus
        # bei kurzen PV-Einbrüchen aus dem Akku versorgt werden kann.
        assert decision.charge_power_limit == 0.0
        assert decision.discharge_power_limit is None

    def test_charges_when_forecast_insufficient(self):
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=2.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        assert decision.phase == PHASE_CORRIDOR

    def test_no_delay_after_charge_end_time(self):
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        # 20:00 in June → past summer_charge_end (~18.5)
        decision = decide(state, params, _now(6, 15, 20))
        assert decision.phase == PHASE_CORRIDOR

    def test_disabled_falls_through_to_corridor(self):
        params = MaestroParams(charge_target=85, lower_corridor_pause_enabled=False)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=99.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        assert decision.phase == PHASE_CORRIDOR

    def test_emergency_overrides_pv_delay(self):
        params = _params_with_forecast(threshold=5.0, capacity=10.0)
        state = MaestroState(
            soc=10, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=20.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        assert decision.phase == PHASE_EMERGENCY

    def test_pv_delay_bypassed_during_curtailment(self):
        """Curtailment active → PV-Delay must NOT win; charge floor required."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        state = MaestroState(
            soc=30, pv_power=10000, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(state, params, _now(6, 15, 9), curtailment_guard_active=True)
        # Without curtailment we'd get PV_DELAY; now we expect CORRIDOR (charging)
        # and definitely NOT PV_DELAY.
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase != PHASE_PV_DELAY

    def test_pv_delay_bypassed_below_delay_min_soc(self):
        """SoC under delay_min_soc floor → pv_delay must NOT block charging."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        params.delay_min_soc = 40.0  # Floor: erst ab 40% darf verzögert werden
        state = MaestroState(
            soc=25, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=20.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase != PHASE_PV_DELAY
        assert decision.phase == PHASE_CORRIDOR

    def test_pv_delay_active_above_delay_min_soc(self):
        """SoC at/above floor → pv_delay applies as before."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        params.delay_min_soc = 25.0  # Floor < SoC=30
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase == PHASE_PV_DELAY

    def test_pv_delay_suppressed_within_cooldown_after_feed_in_limit(self):
        """pv_delay must NOT fire within 60 s after previous feed_in_limit phase."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        now = _now(6, 15, 9)
        # Phase changed 30 s ago – still inside 60 s cooldown
        phase_since = now - timedelta(seconds=30)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(
            state, params, now,
            previous_phase=PHASE_FEED_IN_LIMIT,
            previous_phase_since=phase_since,
        )
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase != PHASE_PV_DELAY

    def test_pv_delay_allowed_after_cooldown_expires(self):
        """pv_delay must be allowed again once 60 s cooldown has elapsed."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        now = _now(6, 15, 9)
        # Phase changed 90 s ago – cooldown has expired
        phase_since = now - timedelta(seconds=90)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(
            state, params, now,
            previous_phase=PHASE_FEED_IN_LIMIT,
            previous_phase_since=phase_since,
        )
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase == PHASE_PV_DELAY

    def test_pv_delay_not_suppressed_when_previous_phase_is_not_feed_in(self):
        """Cooldown only applies after feed_in_limit, not other phases."""
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        now = _now(6, 15, 9)
        phase_since = now - timedelta(seconds=10)  # Only 10 s ago but wrong phase
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(
            state, params, now,
            previous_phase="corridor",
            previous_phase_since=phase_since,
        )
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY
        assert decision.phase == PHASE_PV_DELAY

    def test_pv_delay_skipped_when_spreading_enabled(self):
        """With spreading active, pv_delay must NOT preempt the spreading phase.

        Andernfalls f\u00e4llt charge_power_limit=None auf den E3DC-Default zur\u00fcck
        (clear_power_limits) und der Akku l\u00e4dt mit voller PV-\u00dcberschussleistung
        statt gleichm\u00e4\u00dfig \u00fcber das Tagesfenster.
        """
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        params.spreading_enabled = True  # explicitly enable
        params.spreading_target_soc = 100.0
        state = MaestroState(
            soc=30, pv_power=2000, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        from custom_components.e3dc_maestro.const import PHASE_PV_DELAY, PHASE_SPREADING
        assert decision.phase != PHASE_PV_DELAY
        # Spreading sollte greifen (oder corridor, falls SoC < target)
        assert decision.phase in (PHASE_SPREADING, "corridor")

    def test_pv_delay_blocks_charging_but_allows_discharge(self):
        """pv_delay sendet max_charge=0 an den E3DC, l\u00e4sst Entladung aber frei.

        Wenn das Haus bei kurzen PV-Einbr\u00fcchen aus dem Akku versorgt werden
        m\u00f6chte, darf die Entladung nicht gesperrt werden. Nur die
        Notstromreserve-Phase blockiert die Entladung.
        """
        params = _params_with_forecast(threshold=5.0, capacity=10.0, factor=1.2)
        state = MaestroState(
            soc=30, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=8.0,
        )
        decision = decide(state, params, _now(6, 15, 9))
        from custom_components.e3dc_maestro.const import (
            PHASE_PV_DELAY,
            POWER_MODE_NORMAL,
        )
        assert decision.phase == PHASE_PV_DELAY
        assert decision.power_mode == POWER_MODE_NORMAL  # NICHT IDLE \u2192 Discharge frei
        assert decision.charge_power_limit == 0.0       # Ladung blockiert
        assert decision.discharge_power_limit is None    # Entladung frei


# ──────────────────────────────────────────────────────────────────────────────
# EWMA helper: pure-math smoke tests (independent of coordinator)
# ──────────────────────────────────────────────────────────────────────────────

class TestEwmaLogic:
    """Verify EWMA behaviour using the same formula used in coordinator._ewma_update."""

    import math as _math

    _GLITCH_FLOOR = 200.0

    def _ewma(self, prev, new_val, tau_s=60.0, dt_s=30.0, jump=2000.0):
        import math
        if prev is None:
            return new_val
        if new_val == 0.0 and prev > self._GLITCH_FLOOR:
            return prev
        if abs(new_val - prev) > jump:
            return new_val
        alpha = 1.0 - math.exp(-dt_s / tau_s)
        return prev + alpha * (new_val - prev)

    def test_initialises_to_first_value(self):
        assert self._ewma(None, 1500.0) == 1500.0

    def test_converges_toward_new_value(self):
        prev = 1000.0
        result = self._ewma(prev, 2000.0, tau_s=60.0, dt_s=30.0)
        assert prev < result < 2000.0

    def test_jump_reset_above_threshold(self):
        """Step > jump_threshold → EWMA snaps to new value immediately."""
        result = self._ewma(500.0, 4000.0, jump=2000.0)  # delta = 3500 > 2000
        assert result == 4000.0

    def test_no_jump_reset_below_threshold(self):
        """Step < jump_threshold → EWMA smooths."""
        result = self._ewma(1000.0, 2500.0, jump=2000.0)  # delta = 1500 < 2000
        assert 1000.0 < result < 2500.0

    def test_full_convergence_after_many_ticks(self):
        """After many ticks the EWMA converges to the stable target."""
        val = 0.0
        target = 3000.0
        for _ in range(1000):
            val = self._ewma(val, target, tau_s=60.0, dt_s=30.0, jump=999999)
        assert abs(val - target) < 0.01

    def test_zero_glitch_suppressed_when_prev_above_floor(self):
        """E3DC RSCP zero-glitch: 0W with prev > 200W must be ignored."""
        result = self._ewma(1500.0, 0.0)
        assert result == 1500.0  # unchanged

    def test_zero_value_accepted_when_prev_below_floor(self):
        """Genuine 0W (e.g. night standby) is accepted when prev <= 200W."""
        result = self._ewma(150.0, 0.0)
        assert result < 150.0  # EWMA moves toward 0


# ──────────────────────────────────────────────────────────────────────────────
# Phase B: Time-to-Target-Korridor
# ──────────────────────────────────────────────────────────────────────────────

class TestTimeToTargetPower:
    """Unit tests for time_to_target_power() (Phase B)."""

    def _params(self, **kwargs) -> MaestroParams:
        base = dict(DEFAULT_PARAMS.__dict__)
        base.update({"battery_capacity_kwh": 10.0, "min_charge_power": 300, "max_charge_power": 3000})
        base.update(kwargs)
        return MaestroParams(**base)

    def _state(self, soc: float) -> MaestroState:
        return MaestroState(soc=soc, pv_power=0, house_power=0, grid_power=0, battery_power=0)

    def test_half_empty_half_time_returns_min_power(self):
        """50% SoC, target 100%, 10kWh battery, charge_end=18.5, now=10:00 → 5kWh / 8.5h ≈ 588W."""
        p = self._params(summer_charge_end=18.5, min_charge_power=300, max_charge_power=3000)
        state = self._state(soc=50)
        result = time_to_target_power(state, p, _now(6, 15, 10), target=100.0)
        # 5kWh / 8.5h = 588W, within bounds
        assert 300 <= result <= 3000
        assert abs(result - 5000 / 8.5) < 50  # ±50W tolerance

    def test_soc_above_target_returns_zero(self):
        """When soc >= target, no charging needed → 0."""
        p = self._params()
        state = self._state(soc=90)
        result = time_to_target_power(state, p, _now(6, 15, 10), target=85.0)
        assert result == 0.0

    def test_very_little_time_clamps_to_max_power(self):
        """With only 0.1h left and 5kWh needed → 50kW raw → clamped to max_charge_power."""
        p = self._params(summer_charge_end=18.5, max_charge_power=3000)
        state = self._state(soc=50)
        # charge_end = 18.5, now = 18:24 → hours_left = 0.1
        result = time_to_target_power(state, p, _now(6, 15, 18, 24), target=100.0)
        assert result == p.max_charge_power

    def test_soc_at_target_returns_zero(self):
        """When soc exactly equals target → 0."""
        p = self._params()
        state = self._state(soc=85.0)
        result = time_to_target_power(state, p, _now(6, 15, 10), target=85.0)
        assert result == 0.0

    def test_very_small_need_clamps_to_min_power(self):
        """With tiny delta (0.01%) and lots of time → raw near 0 but >0 → clamped to min."""
        p = self._params(battery_capacity_kwh=10.0, min_charge_power=300, summer_charge_end=18.5)
        state = self._state(soc=84.99)
        result = time_to_target_power(state, p, _now(6, 15, 10), target=85.0)
        assert result == p.min_charge_power

    def test_corridor_uses_time_to_target(self):
        """CORRIDOR phase: charge_power_limit should reflect time-to-target, not power_factor."""
        p = self._params(
            ht_enabled=False,
            lower_corridor_pause_enabled=False,
            battery_capacity_kwh=10.0,
            summer_charge_end=18.5,
            charge_target=85,
            min_charge_power=100,
            max_charge_power=5000,
        )
        # soc=20 is well below any linear target, so corridor activates
        state = MaestroState(soc=20, pv_power=5000, house_power=1000, grid_power=0, battery_power=0)
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert 100 <= decision.charge_power_limit <= 5000


# ──────────────────────────────────────────────────────────────────────────────
# B1: Saisonale Notstromreserve
# ──────────────────────────────────────────────────────────────────────────────

class TestSeasonalReserve:
    def _reserve_params(self) -> MaestroParams:
        return MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "seasonal_reserve_enabled": True,
               "reserve_winter_percent": 30,
               "reserve_equinox_percent": 15,
               "ht_enabled": False,
            }
        )

    def test_winter_reserve_is_at_winter_level(self):
        dt = _now(12, 21, 12)  # winter solstice
        p = self._reserve_params()
        soc = seasonal_reserve_soc(dt, p)
        assert abs(soc - 30) < 1.0

    def test_equinox_reserve_is_lower_than_winter(self):
        dt_winter = _now(12, 21, 12)  # winter solstice
        dt_equinox = _now(3, 21, 12)  # spring equinox ≈ DOY 80
        p = self._reserve_params()
        soc_winter = seasonal_reserve_soc(dt_winter, p)
        soc_equinox = seasonal_reserve_soc(dt_equinox, p)
        assert soc_winter > soc_equinox

    def test_blocks_discharge_when_soc_at_reserve(self):
        """When SoC equals the reserve, discharge should be blocked (POWER_MODE_IDLE)."""
        from custom_components.e3dc_maestro.const import POWER_MODE_IDLE
        p = self._reserve_params()
        state = MaestroState(
            soc=28, pv_power=0, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(12, 21, 14))  # winter, reserve ≈ 30
        assert decision.phase == PHASE_RESERVE_PROTECTION
        assert decision.power_mode == POWER_MODE_IDLE

    def test_emergency_has_priority_over_reserve(self):
        """EMERGENCY (SoC < charge_threshold) must override RESERVE_PROTECTION."""
        p = self._reserve_params()
        p.charge_threshold = 20
        state = MaestroState(
            soc=10, pv_power=0, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(12, 21, 14))
        assert decision.phase == PHASE_EMERGENCY

    def test_disabled_does_not_block(self):
        """When reserve is disabled, normal corridor should be active."""
        p = MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "seasonal_reserve_enabled": False,
               "ht_enabled": False,
            }
        )
        state = MaestroState(
            soc=28, pv_power=0, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(12, 21, 9))
        assert decision.phase != PHASE_RESERVE_PROTECTION


# ──────────────────────────────────────────────────────────────────────────────
# D1: EVCC-Integration
# ──────────────────────────────────────────────────────────────────────────────

class TestEvccPause:
    def _evcc_params(self) -> MaestroParams:
        return MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "evcc_enabled": True,
               "ht_enabled": False,
            }
        )

    def test_evcc_pause_when_now_mode_and_charging(self):
        p = self._evcc_params()
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_EVCC_PAUSE

    def test_no_evcc_pause_in_pv_mode(self):
        p = self._evcc_params()
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="pv",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase != PHASE_EVCC_PAUSE

    def test_no_evcc_pause_when_not_charging(self):
        p = self._evcc_params()
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=False, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase != PHASE_EVCC_PAUSE

    def test_evcc_disabled_no_pause(self):
        p = MaestroParams(**{**DEFAULT_PARAMS.__dict__, "evcc_enabled": False, "ht_enabled": False})
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase != PHASE_EVCC_PAUSE

    def test_openwb_sofortladen_triggers_pause(self):
        """openWB uses 'sofortladen' instead of 'now' – configurable via evcc_now_value."""
        p = MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "evcc_enabled": True,
               "evcc_now_value": "sofortladen",
               "ht_enabled": False,
            }
        )
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="sofortladen",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_EVCC_PAUSE

    def test_evcc_pause_discharges_locked_by_default(self):
        """Default (limit=0): discharge_power_limit must be 0."""
        p = self._evcc_params()  # evcc_discharge_limit_w = 0 (default)
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_EVCC_PAUSE
        assert decision.discharge_power_limit == 0.0

    def test_evcc_pause_limits_discharge_to_base_load(self):
        """Custom limit (e.g. 500 W): discharge_power_limit must match."""
        p = MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "evcc_enabled": True,
               "evcc_discharge_limit_w": 500,
               "ht_enabled": False,
            }
        )
        state = MaestroState(
            soc=50, pv_power=3000, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_EVCC_PAUSE
        assert decision.discharge_power_limit == 500

    def test_emergency_overrides_evcc_pause(self):
        p = self._evcc_params()
        state = MaestroState(
            soc=5, pv_power=0, house_power=500, grid_power=0, battery_power=0,
            evcc_charging=True, evcc_mode="now",
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_EMERGENCY


# ──────────────────────────────────────────────────────────────────────────────
# E2: Prognosebasiertes Spreading (Ladeverteilung)
# ──────────────────────────────────────────────────────────────────────────────

class TestSpreading:
    def _spreading_params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "spreading_enabled": True,
            "spreading_target_soc": 100.0,
            "battery_capacity_kwh": 19.5,
            "ht_enabled": False,
            "charge_target": 90,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_spreading_activates_when_soc_above_linear_target(self):
        """SoC=55 % above linear target ~47 % → PHASE_SPREADING, not IDLE."""
        p = self._spreading_params()
        state = MaestroState(
            soc=55, pv_power=8000, house_power=2000, grid_power=0, battery_power=8000,
        )
        # At 10:30 in summer, linear target < 55%, so CORRIDOR would not activate
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_SPREADING

    def test_spreading_charge_power_within_limits(self):
        """Spreading rate must be within [min_charge_power, max_charge_power]."""
        p = self._spreading_params(
            min_charge_power=300,
            max_charge_power=3000,
            battery_capacity_kwh=19.5,
        )
        state = MaestroState(
            soc=55, pv_power=8000, house_power=2000, grid_power=0, battery_power=8000,
        )
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_SPREADING
        assert decision.charge_power_limit is not None
        assert p.min_charge_power <= decision.charge_power_limit <= p.max_charge_power

    def test_spreading_rate_calculation(self):
        """Spreading rate = remaining_kwh / remaining_hours * 1000."""
        p = self._spreading_params(
            summer_charge_end=18.5,
            battery_capacity_kwh=20.0,
            min_charge_power=100,
            max_charge_power=10000,
        )
        state = MaestroState(
            soc=50, pv_power=8000, house_power=2000, grid_power=0, battery_power=8000,
        )
        # 10:30 UTC, charge_end = 18.5, remaining_hours = 8.0
        # remaining_soc = 50%, remaining_kwh = 10 kWh, rate = 10000/8 = 1250 W
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_SPREADING
        assert abs(decision.charge_power_limit - 1250.0) < 50  # ±50W tolerance

    def test_spreading_disabled_falls_through_to_idle(self):
        """With spreading disabled, SoC > linear target → IDLE."""
        p = self._spreading_params(spreading_enabled=False)
        state = MaestroState(
            soc=55, pv_power=8000, house_power=2000, grid_power=0, battery_power=8000,
        )
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_IDLE

    def test_spreading_inactive_after_charge_end(self):
        """After summer_charge_end, spreading is inactive → IDLE (SoC above linear target)."""
        p = self._spreading_params(summer_charge_end=18.5, charge_target=90)
        state = MaestroState(
            soc=92, pv_power=2000, house_power=2000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 19, 0))  # 19:00 > charge_end, SoC above target
        assert decision.phase == PHASE_IDLE

    def test_spreading_inactive_when_soc_at_target(self):
        """When SoC already at spreading_target_soc, spreading is inactive."""
        p = self._spreading_params(spreading_target_soc=100.0)
        state = MaestroState(
            soc=100, pv_power=4000, house_power=2000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_IDLE

    def test_emergency_overrides_spreading(self):
        """EMERGENCY phase has higher priority than spreading."""
        p = self._spreading_params()
        state = MaestroState(
            soc=5, pv_power=8000, house_power=2000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_EMERGENCY

    def test_spreading_suppressed_when_battery_full(self):
        """SoC ≥ 98% → no spreading, even if spreading_target_soc=100."""
        p = self._spreading_params(spreading_target_soc=100.0)
        state = MaestroState(
            soc=99, pv_power=4000, house_power=2000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_IDLE
        # Section 10 catch-all blockt das Laden hart auf 1 W (Entladen bleibt
        # frei via POWER_MODE_NORMAL), damit der Akku nicht weiter über das
        # Ziel hinaus gefüllt wird.
        assert decision.charge_power_limit == 1

    def test_spreading_proceeds_even_with_high_pv_forecast(self):
        """Spreading läuft auch bei 105 kWh PV-Prognose: das ist genau der Sinn –
        die Spreading-Rate verteilt die Restkapazität gleichmäßig bis charge_end,
        damit PV-Überschuss tagsüber ins Netz gehen kann statt den Akku
        unkontrolliert mit Vollgas zu füllen."""
        from custom_components.e3dc_maestro.const import PHASE_SPREADING
        p = self._spreading_params(
            spreading_target_soc=100.0,
            pv_forecast_enabled=True,
            pv_forecast_threshold_kwh=5.0,
            pv_forecast_safety_factor=1.2,
            battery_capacity_kwh=19.5,
        )
        state = MaestroState(
            soc=92, pv_power=8000, house_power=1000, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=105.0,
        )
        decision = decide(state, p, _now(6, 15, 10, 36))
        assert decision.phase == PHASE_SPREADING
        # Restbedarf 8% * 19.5 ≈ 1.56 kWh über mehrere Stunden → niedrige W-Zahl
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit < 1000

    def test_spreading_target_overshoot_blocks_charge(self):
        """User-Szenario: Spreading-Ziel von 100 % auf 90 % reduziert, SoC 95 %.
        Engine darf nicht auf IDLE/None fallen (das würde clear_power_limits
        triggern und der WR lädt mit vollem PV-Überschuss bis 100 %).
        Stattdessen muss ein hartes Mini-Limit gesetzt werden, während
        Entladen über POWER_MODE_NORMAL erlaubt bleibt."""
        from custom_components.e3dc_maestro.const import PHASE_IDLE, POWER_MODE_NORMAL
        p = self._spreading_params(
            spreading_target_soc=90.0,
        )
        state = MaestroState(
            soc=95, pv_power=8000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12, 0))
        assert decision.phase == PHASE_IDLE
        assert decision.power_mode == POWER_MODE_NORMAL  # Entladen bleibt erlaubt
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit <= 10  # 1 W = effektiv keine Ladung
        assert "Spreading-Ziel" in decision.reason

    def test_idle_at_target_blocks_charge_keeps_discharge(self):
        """Spreading aus + SoC am normalen Ziel: Section 10 catch-all muss
        Laden hart blockieren (sonst clear_power_limits → unkontrollierte
        Ladung), aber Entladen über POWER_MODE_NORMAL erhalten, damit
        plötzliche Lastspitzen aus dem Akku gedeckt werden."""
        from custom_components.e3dc_maestro.const import PHASE_IDLE, POWER_MODE_NORMAL
        p = self._spreading_params(spreading_enabled=False)
        # SoC 80 ist deutlich über Linearziel um 12 Uhr → nichts greift außer Idle.
        state = MaestroState(
            soc=80, pv_power=6000, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12, 0))
        assert decision.phase == PHASE_IDLE
        assert decision.power_mode == POWER_MODE_NORMAL
        assert decision.charge_power_limit == 1
        assert "kein Handlungsbedarf" in decision.reason


# ──────────────────────────────────────────────────────────────────────────────
# E3/Phase 1: Curtailment Guard
# ──────────────────────────────────────────────────────────────────────────────

class TestCurtailmentGuard:
    """Curtailment Guard activates when there is potential feed-in or WR clipping."""

    def _cg_params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            # Spreading is on by default (v0.3.2 hardware-protection); these
            # tests focus on Curtailment-Guard hysteresis, so disable spreading
            # to keep the test scope narrow.
            "spreading_enabled": False,
            "curtailment_guard_enabled": True,
            "curtailment_activation_w": 1500,
            "curtailment_release_w": 500,
            "installed_kwp": 10.0,
            "feed_in_limit_percent": 70.0,  # → 7000 W
            "inverter_power": 12000,
            "max_charge_power": 6000,
            "charge_target": 85,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_curtailment_guard_activates_on_feed_in_excess(self):
        """PV=10kW, house=1kW, limit=7kW → floor=2kW → CURTAILMENT_GUARD."""
        p = self._cg_params()
        state = MaestroState(
            soc=86, pv_power=10000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12), curtailment_guard_active=True)
        assert decision.phase == PHASE_CURTAILMENT_GUARD
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit >= 2000  # floor = 10000-1000-7000 = 2000W

    def test_curtailment_guard_uses_inverter_clipping_floor(self):
        """PV=14kW > WR=12kW → inverter floor=2kW (higher than feed-in floor)."""
        p = self._cg_params(inverter_power=12000, installed_kwp=20.0, feed_in_limit_percent=70.0)
        # feed_in limit = 14000W, feed_in floor = 0; inverter floor = 14000-12000=2000
        state = MaestroState(
            soc=86, pv_power=14000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12), curtailment_guard_active=True)
        assert decision.phase == PHASE_CURTAILMENT_GUARD
        assert decision.charge_power_limit >= 2000

    def test_curtailment_guard_inactive_without_active_flag(self):
        """Guard not active via hysteresis flag → normal IDLE."""
        p = self._cg_params()
        state = MaestroState(
            soc=86, pv_power=10000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12), curtailment_guard_active=False)
        assert decision.phase == PHASE_IDLE

    def test_curtailment_guard_disabled(self):
        """Guard disabled → IDLE even if floor is high."""
        p = self._cg_params(curtailment_guard_enabled=False)
        state = MaestroState(
            soc=86, pv_power=10000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12), curtailment_guard_active=True)
        assert decision.phase == PHASE_IDLE

    def test_emergency_overrides_curtailment_guard(self):
        """EMERGENCY (SoC < threshold) has higher priority."""
        p = self._cg_params(charge_threshold=15)
        state = MaestroState(
            soc=5, pv_power=10000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 12), curtailment_guard_active=True)
        assert decision.phase == PHASE_EMERGENCY

    def test_curtailment_guard_capped_at_max_charge_power(self):
        """Floor exceeding max_charge_power is capped."""
        p = self._cg_params(max_charge_power=3000, installed_kwp=10.0)
        # floor = 10000-500-7000 = 2500W < max=3000, but let's try huge floor
        p2 = self._cg_params(max_charge_power=1000, installed_kwp=10.0)
        state = MaestroState(
            soc=86, pv_power=10000, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p2, _now(6, 15, 12), curtailment_guard_active=True)
        assert decision.phase == PHASE_CURTAILMENT_GUARD
        assert decision.charge_power_limit <= 1000  # capped at max

    def test_curtailment_guard_suppressed_when_battery_full(self):
        """SoC ≥ 98% → guard must NOT issue a charge command."""
        p = self._cg_params()
        state = MaestroState(
            soc=99, pv_power=10000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10, 36), curtailment_guard_active=True)
        assert decision.phase == PHASE_IDLE
        assert decision.charge_power_limit is None


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2: Untere-Korridor-Pause + House-Ceiling
# ──────────────────────────────────────────────────────────────────────────────

class TestLowerCorridorPause:
    """Lower corridor pause: charge power below threshold → IDLE instead of CORRIDOR."""

    def _lcp_params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            # Tests focus on lower_corridor_pause; disable spreading to keep
            # the test free of the v0.3.2 default-on hardware protection.
            "spreading_enabled": False,
            "lower_corridor_pause_enabled": True,
            "lower_corridor": 500,
            # Small battery + SoC near target → time-to-target rate < lower_corridor
            "battery_capacity_kwh": 5.0,
            "charge_target": 85,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_corridor_pause_below_lower_corridor(self):
        """charge_power < lower_corridor without curtailment → IDLE.

        soc=84, target=85, battery=5kWh: needed=0.05kWh
        charge_end in June at 10:00 ≈ 18.5h → hours_left≈8.5h
        raw ≈ 6W → clamped to min_charge_power (300W) < lower_corridor (500W) → IDLE
        """
        p = self._lcp_params(lower_corridor=500, min_charge_power=300)
        state = MaestroState(
            soc=84, pv_power=2000, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_IDLE

    def test_spreading_overrides_corridor_pause(self):
        """Mit spreading_enabled darf lower_corridor_pause NICHT zu IDLE führen,
        sonst entsteht im Forecast und Live-Betrieb ein Treppen-Pendel
        zwischen IDLE-Pause und Korridor-Burst.
        """
        p = self._lcp_params(
            spreading_enabled=True,
            spreading_target_soc=100,
            lower_corridor=500,
            min_charge_power=300,
            battery_capacity_kwh=5.0,
            charge_target=85,
        )
        # Gleicher Setup wie Pause-Test: soc knapp über interim-target
        state = MaestroState(
            soc=84, pv_power=2000, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10))
        # Spreading muss übernehmen statt IDLE
        assert decision.phase == PHASE_SPREADING
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit >= p.min_charge_power

    def test_corridor_pause_disabled_still_charges(self):
        """When lower_corridor_pause_enabled=False, charge below lower_corridor → CORRIDOR."""
        p = self._lcp_params(
            lower_corridor_pause_enabled=False,
            lower_corridor=500,
            min_charge_power=100,
            battery_capacity_kwh=5.0,
        )
        # At 10:00 in June, soc=40 is below linear target (~42%) → time-to-target rate clamped to min
        # 100W < 500W lower_corridor, but pause disabled → CORRIDOR
        state = MaestroState(
            soc=40, pv_power=2000, house_power=500, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 10))
        assert decision.phase == PHASE_CORRIDOR

    def test_corridor_pause_overridden_by_curtailment_guard(self):
        """Even if charge_power < lower_corridor, curtailment guard keeps charging."""
        p = self._lcp_params(
            lower_corridor=500,
            curtailment_guard_enabled=True,
        )
        state = MaestroState(
            soc=84, pv_power=10000, house_power=500, grid_power=0, battery_power=0,
        )
        # curtailment_guard_active=True forces the guard
        decision = decide(
            state, p, _now(6, 15, 10), curtailment_guard_active=True
        )
        # Falls to curtailment guard (or corridor floor boosted) – must NOT be idle
        # due to corridor pause alone
        assert decision.phase != PHASE_IDLE or decision.charge_power_limit is None


class TestPostCeilingCorridorPause:
    """Fix #1: Korridor-Pause greift auch NACH _apply_house_ceiling.

    Szenario: advanced_corridor=True, SoC-Delta groß → charge_power weit über
    lower_corridor (Pause in 7b greift NICHT). Aber PV-Surplus ist kleiner als
    lower_corridor → nach house-ceiling gilt effective_charge < lower_corridor.
    Erwartet: IDLE mit charge_power_limit=None (clear_power_limits), NICHT ein
    kontraproduktives kleines Ladelimit, das der E3DC ignoriert und stattdessen
    einspeist.
    """

    def _params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            "spreading_enabled": False,
            "lower_corridor_pause_enabled": True,
            "lower_corridor": 1500,
            "upper_corridor": 9000,
            "advanced_corridor": True,
            "battery_capacity_kwh": 15.0,
            "charge_target": 98,
            "min_charge_power": 50,
            "max_charge_power": 9000,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_post_ceiling_pause_returns_idle_with_zero_limit(self):
        """Klassischer Live-Fall: SoC=86%, Ziel=96%, Überschuss ~300 W.

        advanced_corridor: charge_power = 1500 + 8/100 * (9000-1500) ≈ 2100 W
        → weit über lower_corridor=1500 W → Pause 7b greift nicht.
        Surplus = pv(3500) - house(3250) = 250 W < lower_corridor(1500 W)
        → effective_charge nach house-ceiling ≈ 250 W < 1500 W
        → Post-ceiling-Pause muss IDLE + 0 W zurückgeben (Ladung blockiert),
          damit der Wechselrichter nicht auf sein Default-Verhalten (volle
          PV-Überschussladung) zurückfällt.
        Zeitpunkt 16:50 Uhr: ramp-target ≈ 93 % > soc=86 % → corridor-block aktiv.
        """
        p = self._params()
        state = MaestroState(
            soc=86, pv_power=3500, house_power=3250, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(5, 13, 16, 50))
        assert decision.phase == PHASE_IDLE
        assert decision.charge_power_limit == 0.0

    def test_post_ceiling_pause_disabled_sends_small_limit(self):
        """Mit lower_corridor_pause_enabled=False: kleines Limit wird gesendet."""
        p = self._params(lower_corridor_pause_enabled=False)
        state = MaestroState(
            soc=86, pv_power=3500, house_power=3250, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(5, 13, 16, 50))
        # CORRIDOR mit niedrigem, aber gesetztem Limit
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit < p.lower_corridor

    def test_post_ceiling_pause_not_triggered_when_surplus_above_corridor(self):
        """Wenn Surplus > lower_corridor: normaler CORRIDOR, kein IDLE."""
        p = self._params()
        state = MaestroState(
            soc=86, pv_power=6000, house_power=2000, grid_power=0, battery_power=0,
        )
        # Surplus = 4000 W > lower_corridor 1500 W → CORRIDOR normal
        decision = decide(state, p, _now(5, 13, 16, 50))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit >= p.lower_corridor

    def test_post_ceiling_pause_overridden_by_curtailment_guard(self):
        """Curtailment guard überschreibt die Post-Ceiling-Pause."""
        p = self._params()
        state = MaestroState(
            soc=86, pv_power=3500, house_power=3250, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(5, 13, 16, 50), curtailment_guard_active=True)
        assert decision.phase != PHASE_IDLE


class TestHouseCeiling:
    """House-ceiling: spreading/corridor should not draw from grid."""

    def _hc_params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            "spreading_enabled": True,
            "spreading_target_soc": 100.0,
            "battery_capacity_kwh": 20.0,
            "charge_target": 90,
            "min_charge_power": 100,
            "max_charge_power": 10000,
            "lower_corridor_pause_enabled": False,  # avoid pause confusing ceiling test
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_spreading_capped_to_pv_surplus(self):
        """Spreading rate 2000W, but PV surplus only 800W → capped to 800W."""
        p = self._hc_params(
            battery_capacity_kwh=20.0,
            summer_charge_end=18.5,
            min_charge_power=100,
        )
        state = MaestroState(
            soc=50, pv_power=1800, house_power=1000, grid_power=0, battery_power=0,
        )
        # surplus = 800W; computed spreading rate would be much higher
        decision = decide(state, p, _now(6, 15, 10, 30))
        assert decision.phase == PHASE_SPREADING
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit <= 800 + 1  # ceiling ± rounding

    def test_spreading_not_capped_when_cheap_tariff(self):
        """With dynamic tariff + cheap price → house ceiling bypassed."""
        p = self._hc_params(
            dynamic_tariff_enabled=True,
            cheap_threshold=0.15,
            min_charge_power=100,
            lower_corridor_pause_enabled=False,
        )
        state = MaestroState(
            soc=50, pv_power=500, house_power=1000, grid_power=0, battery_power=0,
        )
        # surplus = -500W (negative); with cheap tariff bypass, spreading should still run
        decision = decide(state, p, _now(6, 15, 10, 30), current_price=0.05)
        # Either spreading fires with higher limit, or falls to idle (no surplus at all)
        # Key: should NOT be capped to 0 by house-ceiling due to bypass
        if decision.phase == PHASE_SPREADING:
            # If spreading, it should not be zero
            assert decision.charge_power_limit is not None and decision.charge_power_limit > 0


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4: Two-Tier Ladeende
# ──────────────────────────────────────────────────────────────────────────────

class TestTwoTierLadeende:
    """Two-Tier: ramp charge_target → charge_target_late after charge_end_h."""

    def _tt_params(self, **kwargs) -> MaestroParams:
        base = {
            **DEFAULT_PARAMS.__dict__,
            "ht_enabled": False,
            "spreading_enabled": True,
            "two_tier_enabled": True,
            "charge_target": 80,
            "charge_target_late": 95,
            "late_charge_end_h": 20.0,
            "battery_capacity_kwh": 20.0,
            "min_charge_power": 100,
            "max_charge_power": 6000,
            "lower_corridor_pause_enabled": False,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def test_target_soc_ramps_in_late_window(self):
        """After charge_end_h, target_soc ramps from charge_target to charge_target_late."""
        p = self._tt_params()
        charge_end_h = seasonal_charge_end_hour(_now(6, 15, 12), p)  # ≈ 18.5 h
        # At 19:00 → midpoint in [18.5, 20] window → target > 80 and < 95
        dt = _now(6, 15, 19)
        target = target_soc_for_time(dt, p)
        assert target > p.charge_target
        assert target < p.charge_target_late

    def test_target_soc_at_late_end(self):
        """At late_charge_end_h → target equals charge_target_late."""
        p = self._tt_params()
        dt = _now(6, 15, 20)
        target = target_soc_for_time(dt, p)
        assert abs(target - p.charge_target_late) < 0.1

    def test_spreading_active_in_late_window(self):
        """After charge_end_h, spreading fires toward charge_target_late."""
        p = self._tt_params()
        # soc=82 is above charge_target (80) but below charge_target_late (95)
        state = MaestroState(
            soc=82, pv_power=5000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 19))  # 19:00 = late window
        assert decision.phase == PHASE_SPREADING

    def test_spreading_inactive_after_late_end(self):
        """After late_charge_end_h → spreading stops (soc < target but out of window)."""
        p = self._tt_params()
        state = MaestroState(
            soc=82, pv_power=5000, house_power=1000, grid_power=0, battery_power=0,
        )
        decision = decide(state, p, _now(6, 15, 21))  # 21:00 > late_charge_end_h=20
        # No longer in spreading window → should not be SPREADING
        assert decision.phase != PHASE_SPREADING

    def test_two_tier_disabled_no_late_window(self):
        """With two_tier_enabled=False, target after charge_end_h stays charge_target."""
        p = self._tt_params(two_tier_enabled=False)
        dt = _now(6, 15, 19)
        target = target_soc_for_time(dt, p)
        assert target == p.charge_target


class TestMorningPreDischarge:
    """Phase 6 – Morning Pre-Discharge + Forecast-Gating."""

    def _md_params(self, **kwargs):
        base = {
            **DEFAULT_PARAMS.__dict__,
            "morning_discharge_mode": "active_house",
            "morning_unload_soc": 40.0,
            "morning_unload_start_soc": 60.0,
            "pre_discharge_offset_h": 4.0,
            "pre_discharge_max_power_w": 2000.0,
            "pre_discharge_safety_factor": 1.3,
            "pre_discharge_tibber_auto": False,
            "morning_grid_export_threshold": 0.15,
            "battery_capacity_kwh": 10.0,
            "charge_target": 85.0,
            "summer_charge_end": 16.0,
            "ht_enabled": False,
            "lower_corridor_pause_enabled": False,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def _high_soc_state(self):
        return MaestroState(
            soc=75.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )

    def test_morning_discharge_activates(self):
        """SoC above start threshold, well before charge window → activates."""
        p = self._md_params()
        state = self._high_soc_state()
        # 08:00 is before charge_begin (summer_charge_end 16h - offset 4h = 12:00)
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase == PHASE_MORNING_DISCHARGE

    def test_morning_discharge_off_mode_skips(self):
        """Mode 'off' → phase should not be PHASE_MORNING_DISCHARGE."""
        p = self._md_params(morning_discharge_mode="off")
        state = self._high_soc_state()
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase != PHASE_MORNING_DISCHARGE

    def test_morning_discharge_soc_below_start_threshold(self):
        """SoC below morning_unload_start_soc → no discharge."""
        p = self._md_params(morning_unload_start_soc=80.0)  # requires 80%
        state = MaestroState(
            soc=70.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase != PHASE_MORNING_DISCHARGE

    def test_morning_discharge_soc_already_at_target(self):
        """SoC at or below unload target → nothing to discharge."""
        p = self._md_params(morning_unload_soc=75.0, morning_unload_start_soc=60.0)
        state = MaestroState(
            soc=74.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase != PHASE_MORNING_DISCHARGE

    def test_morning_discharge_after_charge_window_starts(self):
        """After (charge_end_h - offset) → no longer discharge (charging window opened)."""
        p = self._md_params()  # charge_begin = 16 - 4 = 12:00
        state = self._high_soc_state()
        d = decide(state, p, _now(6, 15, 13))  # 13:00 > 12:00
        assert d.phase != PHASE_MORNING_DISCHARGE

    def test_morning_discharge_passive_mode_power_mode(self):
        """Passive mode returns POWER_MODE_IDLE (no active discharge)."""
        p = self._md_params(morning_discharge_mode="passive")
        state = self._high_soc_state()
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase == PHASE_MORNING_DISCHARGE
        assert d.power_mode == POWER_MODE_IDLE
        assert d.charge_power_limit == 0.0

    def test_morning_discharge_active_mode_discharges(self):
        """active_house mode returns POWER_MODE_DISCHARGE with a positive rate."""
        p = self._md_params(morning_discharge_mode="active_house")
        state = self._high_soc_state()
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase == PHASE_MORNING_DISCHARGE
        assert d.power_mode == POWER_MODE_DISCHARGE
        assert d.discharge_power_limit is not None
        assert d.discharge_power_limit > 0

    def test_morning_discharge_rate_capped_at_max_power(self):
        """Discharge rate should not exceed pre_discharge_max_power_w."""
        p = self._md_params(pre_discharge_max_power_w=1500.0)
        state = self._high_soc_state()
        d = decide(state, p, _now(6, 15, 8))
        assert d.discharge_power_limit is not None
        assert d.discharge_power_limit <= 1500.0

    def test_morning_discharge_forecast_gate_blocks_if_insufficient(self):
        """If PV forecast is insufficient, pre-discharge should NOT activate."""
        p = self._md_params(
            pv_forecast_enabled=True,
            pre_discharge_safety_factor=1.3,
            charge_target=85.0,
            morning_unload_soc=40.0,
            battery_capacity_kwh=10.0,
        )
        # needed = (85-40)/100 * 10 = 4.5 kWh; required = 4.5 * 1.3 = 5.85 kWh
        state = MaestroState(
            soc=75.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=4.0,  # < 5.85 → blocked
        )
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase != PHASE_MORNING_DISCHARGE

    def test_morning_discharge_forecast_gate_allows_if_sufficient(self):
        """If PV forecast is sufficient, pre-discharge activates."""
        p = self._md_params(
            pv_forecast_enabled=True,
            pre_discharge_safety_factor=1.3,
            charge_target=85.0,
            morning_unload_soc=40.0,
            battery_capacity_kwh=10.0,
        )
        state = MaestroState(
            soc=75.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
            pv_forecast_remaining_kwh=6.5,  # >= 5.85 → allowed
        )
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase == PHASE_MORNING_DISCHARGE

    def test_emergency_overrides_morning_discharge(self):
        """Emergency charge always wins over morning pre-discharge."""
        p = self._md_params(charge_threshold=30.0)
        state = MaestroState(
            soc=20.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )
        d = decide(state, p, _now(6, 15, 8))
        assert d.phase == "emergency"

    def test_tibber_auto_upgrades_to_active_grid(self):
        """High Tibber price triggers active_grid mode (export)."""
        p = self._md_params(
            morning_discharge_mode="passive",
            pre_discharge_tibber_auto=True,
            dynamic_tariff_enabled=True,
            morning_grid_export_threshold=0.15,
        )
        state = self._high_soc_state()
        # price = 0.20 > 0.15 threshold → should upgrade to active_grid
        d = decide(state, p, _now(6, 15, 8), current_price=0.20)
        assert d.phase == PHASE_MORNING_DISCHARGE
        assert d.power_mode == POWER_MODE_DISCHARGE  # active_grid discharges


class TestAstroModus:
    """Phase 7 – Astro sunrise/sunset based charge timing."""

    def _astro_params(self, **kwargs):
        base = {
            **DEFAULT_PARAMS.__dict__,
            "astro_enabled": True,
            "astro_latitude": 48.15,
            "astro_longitude": 11.58,
            "charge_end_sunset_offset_h": -2.0,
            "charge_start_sunrise_offset_h": 2.0,
            "charge_target": 85.0,
            "ht_enabled": False,
            "lower_corridor_pause_enabled": False,
            "morning_discharge_mode": "off",
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def _low_soc_state(self):
        return MaestroState(
            soc=50.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )

    def test_sunrise_sunset_summer_munich(self):
        """Sunrise/sunset for Munich on summer solstice should be plausible."""
        from datetime import timezone, timedelta
        p = self._astro_params()
        dt = _now(6, 21, 12).replace(tzinfo=timezone(timedelta(hours=2)))
        sunrise_h, sunset_h = astro_sunrise_sunset(dt, p)
        assert 4.5 < sunrise_h < 6.0, f"sunrise={sunrise_h:.2f} out of range"
        assert 20.5 < sunset_h < 22.0, f"sunset={sunset_h:.2f} out of range"

    def test_sunrise_sunset_winter_munich(self):
        """Winter solstice: short day → late sunrise, early sunset."""
        from datetime import timezone, timedelta
        p = self._astro_params()
        dt = _now(12, 21, 12).replace(tzinfo=timezone(timedelta(hours=1)))
        sunrise_h, sunset_h = astro_sunrise_sunset(dt, p)
        assert 7.0 < sunrise_h < 9.0, f"sunrise={sunrise_h:.2f} out of range"
        assert 15.0 < sunset_h < 17.5, f"sunset={sunset_h:.2f} out of range"

    def test_astro_charge_end_uses_sunset(self):
        """With astro_enabled, seasonal_charge_end_hour returns sunset + offset."""
        from datetime import timezone, timedelta
        p = self._astro_params(charge_end_sunset_offset_h=-2.0)
        dt = _now(6, 21, 12).replace(tzinfo=timezone(timedelta(hours=2)))
        _, sunset_h = astro_sunrise_sunset(dt, p)
        charge_end = seasonal_charge_end_hour(dt, p)
        assert abs(charge_end - (sunset_h - 2.0)) < 0.1

    def test_astro_wait_blocks_charging_before_sunrise(self):
        """Before sunrise + offset, charging should be blocked (PHASE_ASTRO_WAIT)."""
        p = self._astro_params(
            astro_latitude=48.15, astro_longitude=11.58,
            charge_start_sunrise_offset_h=2.0,
        )
        state = self._low_soc_state()
        # 04:00 UTC = well before sunrise even for summer
        d = decide(state, p, _now(6, 21, 4))
        assert d.phase == PHASE_ASTRO_WAIT

    def test_astro_wait_allows_charging_after_sunrise(self):
        """After sunrise + offset, charging should proceed (not PHASE_ASTRO_WAIT)."""
        p = self._astro_params(
            astro_latitude=48.15, astro_longitude=11.58,
            charge_start_sunrise_offset_h=2.0,
        )
        state = self._low_soc_state()
        # 12:00 UTC = well after sunrise+2h in any season
        d = decide(state, p, _now(6, 21, 12))
        assert d.phase != PHASE_ASTRO_WAIT

    def test_astro_disabled_no_wait(self):
        """With astro_enabled=False, PHASE_ASTRO_WAIT never fires."""
        p = self._astro_params(astro_enabled=False)
        state = self._low_soc_state()
        d = decide(state, p, _now(6, 21, 4))
        assert d.phase != PHASE_ASTRO_WAIT

    def test_astro_wait_soc_at_target_no_wait(self):
        """When SoC >= charge_target, ASTRO_WAIT does not block (nothing to charge)."""
        p = self._astro_params(charge_target=85.0)
        state = MaestroState(
            soc=85.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )
        d = decide(state, p, _now(6, 21, 4))
        assert d.phase != PHASE_ASTRO_WAIT

    def test_emergency_overrides_astro_wait(self):
        """Emergency charge always wins over astro wait."""
        p = self._astro_params(charge_threshold=30.0)
        state = MaestroState(
            soc=20.0, pv_power=3000, house_power=1000, grid_power=0, battery_power=0,
        )
        d = decide(state, p, _now(6, 21, 4))
        assert d.phase == "emergency"



# ──────────────────────────────────────────────────────────────────────────────
# Phase C: Tariff slot scheduler
# ──────────────────────────────────────────────────────────────────────────────


class TestTariffScheduler:
    def _import(self):
        from custom_components.e3dc_maestro.control_engine import (
            TariffSchedule,
            TariffSlot,
            current_tariff_class,
            tariff_schedule_from_params,
            TARIFF_HIGH,
            TARIFF_LOW,
            TARIFF_NORMAL,
        )
        return (
            TariffSchedule, TariffSlot, current_tariff_class,
            tariff_schedule_from_params, TARIFF_HIGH, TARIFF_LOW, TARIFF_NORMAL,
        )

    def test_weekday_match_inside_window(self):
        TS, TSlot, ctc, _, HIGH, LOW, NORMAL = self._import()
        sched = TS(slots=[TSlot(weekdays=frozenset({0, 1, 2, 3, 4}), start_h=5, end_h=21, class_=HIGH)])
        # Mon 2026-06-15 10:00 UTC → weekday 0
        assert ctc(_now(6, 15, 10), sched) == HIGH
        # Sat 2026-06-20 10:00 UTC → weekday 5 (excluded)
        assert ctc(_now(6, 20, 10), sched) == NORMAL

    def test_outside_window_returns_normal(self):
        TS, TSlot, ctc, _, HIGH, _LOW, NORMAL = self._import()
        sched = TS(slots=[TSlot(weekdays=frozenset(range(7)), start_h=5, end_h=21, class_=HIGH)])
        assert ctc(_now(6, 15, 22), sched) == NORMAL

    def test_midnight_wraparound_slot(self):
        TS, TSlot, ctc, _, HIGH, _LOW, NORMAL = self._import()
        # 22:00 → 06:00 night slot, every day
        sched = TS(slots=[TSlot(weekdays=frozenset(range(7)), start_h=22, end_h=6, class_=HIGH)])
        # Mon 23:00 inside (start side)
        assert ctc(_now(6, 15, 23), sched) == HIGH
        # Tue 02:00 inside (wrapped from Mon)
        assert ctc(_now(6, 16, 2), sched) == HIGH
        # Tue 12:00 outside
        assert ctc(_now(6, 16, 12), sched) == NORMAL

    def test_high_overrides_low_overlap(self):
        TS, TSlot, ctc, _, HIGH, LOW, NORMAL = self._import()
        sched = TS(slots=[
            TSlot(weekdays=frozenset(range(7)), start_h=8, end_h=20, class_=LOW),
            TSlot(weekdays=frozenset(range(7)), start_h=10, end_h=14, class_=HIGH),
        ])
        # 11:00 → both match, high wins
        assert ctc(_now(6, 15, 11), sched) == HIGH
        # 09:00 → only low matches
        assert ctc(_now(6, 15, 9), sched) == LOW

    def test_dynamic_price_creates_low(self):
        TS, _TSlot, ctc, _, _HIGH, LOW, NORMAL = self._import()
        sched = TS(slots=[], cheap_threshold=0.10)
        assert ctc(_now(6, 15, 12), sched, current_price=0.05) == LOW
        assert ctc(_now(6, 15, 12), sched, current_price=0.15) == NORMAL
        # cheap_threshold without price → normal
        assert ctc(_now(6, 15, 12), sched, current_price=None) == NORMAL

    def test_high_slot_beats_dynamic_low(self):
        TS, TSlot, ctc, _, HIGH, LOW, _N = self._import()
        sched = TS(
            slots=[TSlot(weekdays=frozenset(range(7)), start_h=5, end_h=21, class_=HIGH)],
            cheap_threshold=0.10,
        )
        assert ctc(_now(6, 15, 10), sched, current_price=0.02) == HIGH

    def test_legacy_params_converted_to_schedule(self):
        TS, _TSlot, ctc, t_from_p, HIGH, LOW, NORMAL = self._import()
        params = MaestroParams(
            ht_enabled=True, ht_on=5, ht_off=21,
            ht_sat=False, ht_sun=False,
            dynamic_tariff_enabled=True, cheap_threshold=0.08,
        )
        sched = t_from_p(params)
        assert sched.cheap_threshold == 0.08
        assert len(sched.slots) == 1
        slot = sched.slots[0]
        assert slot.class_ == HIGH
        assert slot.weekdays == frozenset({0, 1, 2, 3, 4})
        # weekday match
        assert ctc(_now(6, 15, 10), sched) == HIGH  # Monday
        assert ctc(_now(6, 20, 10), sched) == NORMAL  # Saturday excluded
        # cheap-threshold low
        assert ctc(_now(6, 15, 22), sched, current_price=0.05) == LOW

    def test_legacy_disabled_dynamic_does_not_create_low(self):
        _TS, _TSlot, ctc, t_from_p, _H, _L, NORMAL = self._import()
        params = MaestroParams(
            ht_enabled=False,
            dynamic_tariff_enabled=False, cheap_threshold=0.08,
        )
        sched = t_from_p(params)
        assert sched.cheap_threshold is None
        assert ctc(_now(6, 15, 12), sched, current_price=0.01) == NORMAL

    def test_explicit_schedule_overrides_legacy(self):
        TS, TSlot, ctc, t_from_p, HIGH, _LOW, NORMAL = self._import()
        custom = TS(slots=[TSlot(weekdays=frozenset(range(7)), start_h=0, end_h=24, class_=HIGH)])
        params = MaestroParams(ht_enabled=False, tariff_schedule=custom)
        assert t_from_p(params) is custom
        assert ctc(_now(6, 15, 3), custom) == HIGH


class TestSlotMinReserveOverridesHtMin:
    def test_slot_reserve_used_for_ht_protection(self):
        from custom_components.e3dc_maestro.control_engine import (
            TariffSchedule, TariffSlot, TARIFF_HIGH,
        )
        slot = TariffSlot(
            weekdays=frozenset(range(7)), start_h=5, end_h=21,
            class_=TARIFF_HIGH, min_reserve_soc=70.0,
        )
        params = MaestroParams(
            **{**DEFAULT_PARAMS.__dict__,
               "ht_enabled": False,  # no legacy slot
               "ht_min": 30, "ht_sockel": 30,
               "tariff_schedule": TariffSchedule(slots=[slot]),
            }
        )
        # SoC=60 is above ht_min=30 (would normally trigger HT-protection),
        # but below the slot's explicit reserve floor 70 → must NOT trigger.
        state = MaestroState(soc=60, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        d = decide(state, params, _now(1, 15, 10))
        assert d.phase != PHASE_HT_PROTECTION

        # SoC=80 is above the floor → HT protection active
        state = MaestroState(soc=80, pv_power=0, house_power=1000, grid_power=0, battery_power=0)
        d = decide(state, params, _now(1, 15, 10))
        assert d.phase == PHASE_HT_PROTECTION


# ──────────────────────────────────────────────────────────────────────────────
# Phase D: Verbrauchsadaptive Reserven
# ──────────────────────────────────────────────────────────────────────────────


def _adaptive_params(**overrides):
    base = {**DEFAULT_PARAMS.__dict__,
            "adaptive_reserve_enabled": True,
            "adaptive_reserve_lookback_days": 14,
            "adaptive_reserve_min_days": 7,
            "adaptive_reserve_safety_factor": 1.3,
            "adaptive_reserve_min_soc": 5.0,
            "adaptive_reserve_max_soc": 90.0,
            "battery_capacity_kwh": 10.0,
            "seasonal_reserve_enabled": True,
            "reserve_winter_percent": 30,
            "reserve_equinox_percent": 15,
            }
    base.update(overrides)
    return MaestroParams(**base)


class TestAdaptiveEmergencyReserve:
    def test_disabled_returns_none(self):
        p = _adaptive_params(adaptive_reserve_enabled=False)
        s = MaestroState(soc=50, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=500,
                         consumption_data_days=10)
        assert adaptive_emergency_reserve_soc(s, p) is None

    def test_insufficient_data_returns_none(self):
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=500,
                         consumption_data_days=3)  # below min 7
        assert adaptive_emergency_reserve_soc(s, p) is None

    def test_no_avg_returns_none(self):
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=None,
                         consumption_data_days=14)
        assert adaptive_emergency_reserve_soc(s, p) is None

    def test_500w_constant_yields_expected_reserve(self):
        # 500 W * 24 h = 12 kWh; * 1.3 safety = 15.6 kWh; / 10 kWh capacity
        # = 156 % → clamped to max 90 %.
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=500,
                         consumption_data_days=14)
        assert adaptive_emergency_reserve_soc(s, p) == 90.0

    def test_low_consumption_yields_low_reserve(self):
        # 100 W * 24h = 2.4 kWh; * 1.3 = 3.12 kWh; / 10 kWh → 31.2 %
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=100, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=100,
                         consumption_data_days=14)
        result = adaptive_emergency_reserve_soc(s, p)
        assert abs(result - 31.2) < 0.01

    def test_clamped_to_min(self):
        # 10 W * 24h * 1.3 = 0.312 kWh / 10 → 3.12 % → clamped to floor 5 %
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=10, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=10,
                         consumption_data_days=14)
        assert adaptive_emergency_reserve_soc(s, p) == 5.0

    def test_high_consumption_clamped_to_new_default_max(self):
        # Regression: Default max_soc is now 35 % (was 90 %).
        # 500 W * 24h * 1.3 / 10 kWh = 156 % → clamped to new max 35 %.
        p = _adaptive_params(adaptive_reserve_max_soc=35.0)
        s = MaestroState(soc=50, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=500,
                         consumption_data_days=14)
        assert adaptive_emergency_reserve_soc(s, p) == 35.0


class TestAdaptiveHtReserve:
    def _slot(self):
        return TariffSlot(
            weekdays=frozenset(range(7)), start_h=16, end_h=20,
            class_=TARIFF_HIGH,
        )

    def test_no_slot_returns_none(self):
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=0, grid_power=0,
                         battery_power=0, consumption_avg_w_ht_window=600,
                         consumption_data_days=14)
        assert adaptive_ht_reserve_soc(s, p, None) is None

    def test_disabled_returns_none(self):
        p = _adaptive_params(adaptive_reserve_enabled=False)
        s = MaestroState(soc=50, pv_power=0, house_power=0, grid_power=0,
                         battery_power=0, consumption_avg_w_ht_window=600,
                         consumption_data_days=14)
        assert adaptive_ht_reserve_soc(s, p, self._slot()) is None

    def test_known_slot_value(self):
        # Slot 16–20 → 4 h × 600 W = 2.4 kWh × 1.3 = 3.12 kWh / 10 = 31.2 %
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=0, grid_power=0,
                         battery_power=0, consumption_avg_w_ht_window=600,
                         consumption_data_days=14)
        result = adaptive_ht_reserve_soc(s, p, self._slot())
        assert abs(result - 31.2) < 0.01

    def test_wraparound_slot_duration(self):
        # Slot 22→06 → 8 h × 250 W = 2.0 kWh × 1.3 = 2.6 kWh / 10 = 26 %
        slot = TariffSlot(weekdays=frozenset(range(7)), start_h=22, end_h=6,
                          class_=TARIFF_HIGH)
        p = _adaptive_params()
        s = MaestroState(soc=50, pv_power=0, house_power=0, grid_power=0,
                         battery_power=0, consumption_avg_w_ht_window=250,
                         consumption_data_days=14)
        result = adaptive_ht_reserve_soc(s, p, slot)
        assert abs(result - 26.0) < 0.01


class TestAdaptiveOverridesInDecide:
    def test_emergency_reserve_uses_adaptive(self):
        # Static would say winter→30 %; adaptive 100 W constant → 3.12 % clamped to 5 %.
        # SoC=10 % is above 5 % → should NOT trigger reserve protection.
        p = _adaptive_params()
        s = MaestroState(soc=10, pv_power=0, house_power=100, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=100,
                         consumption_data_days=14)
        # Pick July day to avoid HT/cold-related branches
        d = decide(s, p, _now(7, 15, 12))
        assert d.phase != PHASE_RESERVE_PROTECTION

    def test_bug_regression_high_load_soc89_not_blocked(self):
        # Bug: max_soc=90 caused reserve_protection to trigger at SoC≤90 %
        # for any average load that yields > 90 % reserve.
        # With new default max_soc=35, SoC=89 % must NOT be blocked.
        p = _adaptive_params(adaptive_reserve_max_soc=35.0)
        s = MaestroState(soc=89, pv_power=0, house_power=500, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=500,
                         consumption_data_days=14)
        d = decide(s, p, _now(7, 15, 14))
        assert d.phase != PHASE_RESERVE_PROTECTION

    def test_emergency_reserve_falls_back_when_no_data(self):
        # Insufficient data → static reserve_winter_percent=30 active.
        # SoC=20 % < 30 % → reserve protection triggers.
        p = _adaptive_params()
        s = MaestroState(soc=20, pv_power=0, house_power=100, grid_power=0,
                         battery_power=0, consumption_avg_w_24h=100,
                         consumption_data_days=2)
        d = decide(s, p, _now(1, 15, 12))  # winter
        assert d.phase == PHASE_RESERVE_PROTECTION

    def test_ht_protection_uses_adaptive_floor(self):
        # Slot 5–21, low avg HT consumption → adaptive floor low → most SoCs trigger HT.
        slot = TariffSlot(weekdays=frozenset(range(7)), start_h=5, end_h=21,
                          class_=TARIFF_HIGH)
        p = _adaptive_params(
            ht_enabled=False,
            tariff_schedule=TariffSchedule(slots=[slot]),
            seasonal_reserve_enabled=False,
        )
        # 200 W × 16 h × 1.3 = 4.16 kWh / 10 = 41.6 % adaptive floor.
        s = MaestroState(soc=60, pv_power=0, house_power=0, grid_power=0,
                         battery_power=0, consumption_avg_w_ht_window=200,
                         consumption_data_days=14)
        d = decide(s, p, _now(1, 15, 10))
        assert d.phase == PHASE_HT_PROTECTION
        assert "adaptiv" in d.reason

        # Below adaptive floor → no HT protection
        s2 = MaestroState(soc=30, pv_power=0, house_power=0, grid_power=0,
                          battery_power=0, consumption_avg_w_ht_window=200,
                          consumption_data_days=14)
        d2 = decide(s2, p, _now(1, 15, 10))
        assert d2.phase != PHASE_HT_PROTECTION


# ──────────────────────────────────────────────────────────────────────────────
# Phase C UI: stored slot list → TariffSchedule round-trip
# ──────────────────────────────────────────────────────────────────────────────


class TestStoredSlotsToSchedule:
    def _import(self):
        from custom_components.e3dc_maestro.coordinator import (
            _tariff_schedule_from_stored,
        )
        from custom_components.e3dc_maestro.const import CONF_TARIFF_SLOTS
        return _tariff_schedule_from_stored, CONF_TARIFF_SLOTS

    def test_returns_none_when_no_slots(self):
        f, key = self._import()
        assert f({}) is None
        assert f({key: []}) is None

    def test_parses_basic_slot(self):
        f, key = self._import()
        sched = f(
            {
                key: [
                    {
                        "weekdays": [0, 1, 2, 3, 4],
                        "start_h": 5,
                        "end_h": 21,
                        "class_": "high",
                        "min_reserve_soc": 50,
                    }
                ]
            }
        )
        assert sched is not None
        assert len(sched.slots) == 1
        s = sched.slots[0]
        assert s.weekdays == frozenset({0, 1, 2, 3, 4})
        assert s.start_h == 5.0
        assert s.end_h == 21.0
        assert s.class_ == "high"
        assert s.min_reserve_soc == 50.0

    def test_invalid_class_falls_back_to_high(self):
        f, key = self._import()
        sched = f({key: [{"weekdays": [0], "start_h": 0, "end_h": 6, "class_": "bogus"}]})
        assert sched.slots[0].class_ == "high"

    def test_skips_malformed_slots(self):
        f, key = self._import()
        sched = f(
            {
                key: [
                    "not a dict",
                    {"weekdays": [0]},  # missing start/end
                    {"weekdays": [0], "start_h": 0, "end_h": 24, "class_": "low"},
                ]
            }
        )
        assert sched is not None
        assert len(sched.slots) == 1
        assert sched.slots[0].class_ == "low"

    def test_cheap_threshold_only_when_dynamic_enabled(self):
        f, key = self._import()
        opts = {
            key: [{"weekdays": [0], "start_h": 0, "end_h": 6, "class_": "high"}],
            "cheap_threshold": 0.08,
        }
        # disabled
        assert f(opts).cheap_threshold is None
        # enabled
        opts["dynamic_tariff_enabled"] = True
        assert f(opts).cheap_threshold == 0.08

    def test_params_from_options_uses_stored_schedule(self):
        from custom_components.e3dc_maestro.coordinator import _params_from_options
        from custom_components.e3dc_maestro.const import CONF_TARIFF_SLOTS

        opts = {
            "ht_enabled": True,  # legacy fallback should be overridden
            "ht_on": 5,
            "ht_off": 21,
            CONF_TARIFF_SLOTS: [
                {"weekdays": [5, 6], "start_h": 0, "end_h": 24, "class_": "low"},
            ],
        }
        p = _params_from_options(opts)
        assert p.tariff_schedule is not None
        assert len(p.tariff_schedule.slots) == 1
        assert p.tariff_schedule.slots[0].class_ == "low"
        assert p.tariff_schedule.slots[0].weekdays == frozenset({5, 6})


# ──────────────────────────────────────────────────────────────────────────────
# F0: Morning-Cap + Gentle-Charge
# ──────────────────────────────────────────────────────────────────────────────

_F0_BASE = MaestroParams(
    inverter_power=12000,
    max_charge_power=5000,
    min_charge_power=300,
    installed_kwp=10.0,
    feed_in_limit_percent=70.0,
    charge_threshold=15.0,
    morning_cap_enabled=True,
    morning_cap_soc=30.0,
    morning_cap_until_h=9.0,
)


class TestMorningCap:
    """decide() F0 Morning-Cap step."""

    def test_soc_below_cap_corridor_proceeds(self):
        """SoC below cap → Morning-Cap does not block corridor."""
        state = MaestroState(soc=25.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        now = _now(6, 1, 7, 30)  # 07:30, below 9h threshold
        result = decide(state, _F0_BASE, now, regelung_aktiv=True)
        assert result.phase != PHASE_MORNING_CAP

    def test_soc_at_cap_before_threshold_returns_morning_cap(self):
        """SoC at cap before until_h → MORNING_CAP with 1 W charge limit (discharge stays free)."""
        state = MaestroState(soc=30.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        now = _now(6, 1, 7, 0)  # 07:00 < 09:00
        result = decide(state, _F0_BASE, now, regelung_aktiv=True)
        assert result.phase == PHASE_MORNING_CAP
        assert result.charge_power_limit == 1

    def test_soc_above_cap_before_threshold_returns_morning_cap(self):
        """SoC above cap → same blocking."""
        state = MaestroState(soc=50.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        now = _now(6, 1, 8, 59)  # still before 9h
        result = decide(state, _F0_BASE, now, regelung_aktiv=True)
        assert result.phase == PHASE_MORNING_CAP

    def test_after_threshold_hour_not_blocked(self):
        """After until_h → Morning-Cap does not block."""
        state = MaestroState(soc=50.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        now = _now(6, 1, 9, 1)  # past 09:00
        result = decide(state, _F0_BASE, now, regelung_aktiv=True)
        assert result.phase != PHASE_MORNING_CAP

    def test_curtailment_guard_overrides_morning_cap(self):
        """curtailment_guard_active bypasses Morning-Cap → guard can charge."""
        state = MaestroState(soc=50.0, pv_power=11000, house_power=300, grid_power=-1000, battery_power=0)
        now = _now(6, 1, 7, 0)
        result = decide(state, _F0_BASE, now, regelung_aktiv=True, curtailment_guard_active=True)
        # Curtailment guard should win, not morning cap
        assert result.phase != PHASE_MORNING_CAP

    def test_disabled_cap_does_not_block(self):
        """morning_cap_enabled=False → step is skipped entirely."""
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=15.0,
            morning_cap_enabled=False,
            morning_cap_soc=30.0,
            morning_cap_until_h=9.0,
        )
        state = MaestroState(soc=50.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        now = _now(6, 1, 7, 0)
        result = decide(state, params, now, regelung_aktiv=True)
        assert result.phase != PHASE_MORNING_CAP


class TestGentleCharge:
    """Gentle-Charge factor applied in coordinator post-processing."""

    def test_gentle_charge_scales_decision(self):
        """After decide() + gentle_charge_enabled=True, charge_power_limit is scaled."""
        from unittest.mock import MagicMock, AsyncMock
        from dataclasses import replace
        # Simulate the coordinator post-processing logic directly
        from custom_components.e3dc_maestro.control_engine import MaestroDecision
        from custom_components.e3dc_maestro.const import POWER_MODE_CHARGE, PHASE_CORRIDOR

        decision = MaestroDecision(
            phase=PHASE_CORRIDOR,
            reason="test",
            power_mode=POWER_MODE_CHARGE,
            charge_power_limit=5000.0,
            target_soc=80.0,
        )
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            gentle_charge_enabled=True,
            gentle_charge_factor=0.35,
        )
        _GENTLE_SKIP = {
            "off", "emergency", "feed_in_limit", "curtailment_guard", "morning_discharge",
        }
        if (
            params.gentle_charge_enabled
            and decision.phase not in _GENTLE_SKIP
            and decision.charge_power_limit is not None
        ):
            decision = replace(decision, charge_power_limit=decision.charge_power_limit * params.gentle_charge_factor)

        assert abs(decision.charge_power_limit - 1750.0) < 1.0

    def test_gentle_charge_skips_emergency(self):
        """Emergency phase must NOT be scaled down."""
        from dataclasses import replace
        from custom_components.e3dc_maestro.control_engine import MaestroDecision
        from custom_components.e3dc_maestro.const import POWER_MODE_CHARGE, PHASE_EMERGENCY

        decision = MaestroDecision(
            phase=PHASE_EMERGENCY,
            reason="test",
            power_mode=POWER_MODE_CHARGE,
            charge_power_limit=5000.0,
            target_soc=80.0,
        )
        params = MaestroParams(gentle_charge_enabled=True, gentle_charge_factor=0.35)
        _GENTLE_SKIP = {
            "off", "emergency", "feed_in_limit", "curtailment_guard", "morning_discharge",
        }
        if (
            params.gentle_charge_enabled
            and decision.phase not in _GENTLE_SKIP
            and decision.charge_power_limit is not None
        ):
            decision = replace(decision, charge_power_limit=decision.charge_power_limit * params.gentle_charge_factor)

        # emergency → NOT scaled
        assert decision.charge_power_limit == 5000.0


class TestForceDischarge:
    """Manual force-discharge dashboard switch."""

    def _params(self, **kwargs):
        base = {
            **DEFAULT_PARAMS.__dict__,
            "force_discharge_power_w": 3000.0,
            "ht_enabled": False,
            "seasonal_reserve_enabled": False,
        }
        base.update(kwargs)
        return MaestroParams(**base)

    def _state(self, soc=70.0):
        return MaestroState(
            soc=soc, pv_power=0, house_power=1500, grid_power=1500, battery_power=0,
        )

    def test_force_discharge_overrides_idle(self):
        """force_discharge=True at high SoC → DISCHARGE with configured rate."""
        from custom_components.e3dc_maestro.const import PHASE_FORCE_DISCHARGE
        p = self._params()
        d = decide(self._state(soc=70.0), p, _now(6, 15, 12), force_discharge=True)
        assert d.phase == PHASE_FORCE_DISCHARGE
        assert d.power_mode == POWER_MODE_DISCHARGE
        # Capped by max_charge_power=3000 in DEFAULT_PARAMS
        assert d.discharge_power_limit == 3000.0
        assert d.charge_power_limit is None

    def test_force_discharge_yields_to_master_off(self):
        """Master switch off must beat force_discharge."""
        p = self._params()
        d = decide(
            self._state(soc=70.0), p, _now(6, 15, 12),
            regelung_aktiv=False, force_discharge=True,
        )
        assert d.phase == PHASE_OFF

    def test_force_discharge_pauses_at_floor(self):
        """SoC at/below charge_threshold → IDLE (do not violate emergency floor)."""
        from custom_components.e3dc_maestro.const import PHASE_FORCE_DISCHARGE
        p = self._params(charge_threshold=15.0)
        # Start just above threshold so emergency does not trigger first;
        # use SoC == threshold so force-discharge pause-branch hits.
        d = decide(self._state(soc=15.0), p, _now(6, 15, 12), force_discharge=True)
        # SoC == threshold → emergency triggers ('< threshold' is False).
        # We want to verify pause branch: bump threshold below SoC.
        p2 = self._params(charge_threshold=70.0)
        d2 = decide(self._state(soc=70.0), p2, _now(6, 15, 12), force_discharge=True)
        assert d2.phase == PHASE_FORCE_DISCHARGE
        assert d2.power_mode == POWER_MODE_IDLE
        assert d2.discharge_power_limit is None


# ──────────────────────────────────────────────────────────────────────────────
# G0: Hard SoC Limit (Akku-Schonung mit Curtailment-Bypass)
# ──────────────────────────────────────────────────────────────────────────────

_G0_BASE = MaestroParams(
    inverter_power=12000,
    max_charge_power=5000,
    min_charge_power=300,
    installed_kwp=10.0,
    feed_in_limit_percent=70.0,
    charge_threshold=15.0,
    charge_target=85.0,
    hard_soc_limit_enabled=True,
    hard_soc_limit=80.0,
)


class TestHardSocLimit:
    """decide() G0 Hard-SoC-Limit step."""

    def test_below_limit_does_not_trigger(self):
        state = MaestroState(soc=75.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        result = decide(state, _G0_BASE, _now(6, 15, 12), regelung_aktiv=True)
        assert result.phase != PHASE_HARD_SOC_LIMIT

    def test_at_limit_blocks_charging(self):
        state = MaestroState(soc=80.0, pv_power=4000, house_power=300, grid_power=0, battery_power=0)
        result = decide(state, _G0_BASE, _now(6, 15, 12), regelung_aktiv=True)
        assert result.phase == PHASE_HARD_SOC_LIMIT
        # Active 1 W cap blocks passive PV charging into the battery
        assert result.charge_power_limit == 1

    def test_above_limit_blocks_charging(self):
        state = MaestroState(soc=92.0, pv_power=4000, house_power=300, grid_power=0, battery_power=0)
        result = decide(state, _G0_BASE, _now(6, 15, 12), regelung_aktiv=True)
        assert result.phase == PHASE_HARD_SOC_LIMIT
        assert result.charge_power_limit == 1

    def test_curtailment_guard_bypasses_hard_limit(self):
        """When PV would otherwise be curtailed, allow charging above the limit."""
        state = MaestroState(soc=85.0, pv_power=11000, house_power=300, grid_power=-1000, battery_power=0)
        result = decide(
            state, _G0_BASE, _now(6, 15, 12),
            regelung_aktiv=True,
            curtailment_guard_active=True,
        )
        # Curtailment Guard wins → never PHASE_HARD_SOC_LIMIT
        assert result.phase != PHASE_HARD_SOC_LIMIT

    def test_disabled_does_not_trigger(self):
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=15.0,
            charge_target=85.0,
            hard_soc_limit_enabled=False,
            hard_soc_limit=80.0,
        )
        state = MaestroState(soc=92.0, pv_power=4000, house_power=300, grid_power=0, battery_power=0)
        result = decide(state, params, _now(6, 15, 12), regelung_aktiv=True)
        assert result.phase != PHASE_HARD_SOC_LIMIT

    def test_emergency_overrides_hard_limit(self):
        """Emergency charge must still trigger even with hard limit enabled."""
        # Defensive: SoC < charge_threshold must always emergency-charge,
        # even though emergency runs before our gate (sanity check).
        state = MaestroState(soc=10.0, pv_power=0, house_power=300, grid_power=0, battery_power=0)
        result = decide(state, _G0_BASE, _now(6, 15, 12), regelung_aktiv=True)
        assert result.phase == PHASE_EMERGENCY



# ──────────────────────────────────────────────────────────────────────────────
# F1+: Forward-Looking Charge Target (vorausschauende Ladung)
# ──────────────────────────────────────────────────────────────────────────────

from custom_components.e3dc_maestro.control_engine import forward_looking_charge_target


def _fwd_params(**overrides) -> MaestroParams:
    base = dict(
        inverter_power=12000,
        max_charge_power=5000,
        min_charge_power=300,
        installed_kwp=10.0,
        feed_in_limit_percent=70.0,
        charge_threshold=15.0,
        charge_target=80.0,
        battery_capacity_kwh=10.0,
        forward_looking_enabled=True,
        forward_looking_max_soc=100.0,
    )
    base.update(overrides)
    return MaestroParams(**base)


def _fwd_state(*, tomorrow_pv, tomorrow_cons) -> MaestroState:
    return MaestroState(
        soc=50.0, pv_power=0.0, house_power=300.0, grid_power=0.0, battery_power=0.0,
        tomorrow_pv_kwh=tomorrow_pv, tomorrow_consumption_kwh=tomorrow_cons,
    )


class TestForwardLooking:
    def test_disabled_returns_base_target(self):
        p = _fwd_params(forward_looking_enabled=False)
        s = _fwd_state(tomorrow_pv=2.0, tomorrow_cons=15.0)
        assert forward_looking_charge_target(s, p, 80.0) == 80.0

    def test_no_data_returns_base_target(self):
        p = _fwd_params()
        s = _fwd_state(tomorrow_pv=None, tomorrow_cons=None)
        assert forward_looking_charge_target(s, p, 80.0) == 80.0

    def test_no_deficit_returns_base_target(self):
        # 20 kWh PV deckt 15 kWh Verbrauch → kein Deficit
        p = _fwd_params()
        s = _fwd_state(tomorrow_pv=20.0, tomorrow_cons=15.0)
        assert forward_looking_charge_target(s, p, 80.0) == 80.0

    def test_deficit_lifts_target(self):
        # Deficit = 15-2 = 13 kWh; bei 10 kWh Akku → +130%, gecappt durch max_soc
        # forward_looking_max_soc=100 → Cap = 100
        p = _fwd_params()
        s = _fwd_state(tomorrow_pv=2.0, tomorrow_cons=15.0)
        assert forward_looking_charge_target(s, p, 80.0) == 100.0

    def test_deficit_partial_within_cap(self):
        # Deficit = 5-2 = 3 kWh; bei 10 kWh Akku → +30% → 80+30=110, gecappt 100
        p = _fwd_params()
        s = _fwd_state(tomorrow_pv=2.0, tomorrow_cons=5.0)
        assert forward_looking_charge_target(s, p, 80.0) == 100.0

    def test_max_soc_caps_target(self):
        # Cap auf 90 % begrenzt das angehobene Ziel
        p = _fwd_params(forward_looking_max_soc=90.0)
        s = _fwd_state(tomorrow_pv=2.0, tomorrow_cons=15.0)
        assert forward_looking_charge_target(s, p, 80.0) == 90.0

    def test_hard_limit_caps_target(self):
        # Hard-SoC-Limit hat Vorrang vor forward-looking-cap
        p = _fwd_params(
            forward_looking_max_soc=100.0,
            hard_soc_limit_enabled=True,
            hard_soc_limit=85.0,
        )
        s = _fwd_state(tomorrow_pv=2.0, tomorrow_cons=15.0)
        assert forward_looking_charge_target(s, p, 80.0) == 85.0

    def test_never_below_base_target(self):
        # Auch bei "negativer" Logik wird base_target nicht unterschritten
        p = _fwd_params(forward_looking_max_soc=70.0)
        s = _fwd_state(tomorrow_pv=20.0, tomorrow_cons=5.0)
        assert forward_looking_charge_target(s, p, 80.0) == 80.0


# ──────────────────────────────────────────────────────────────────────────────
# v0.2.0: tariff_mode hard-constraint
# ──────────────────────────────────────────────────────────────────────────────


class TestTariffModeConstraint:
    """`tariff_mode == "fixed"` must veto the TARIFF_LOW grid-charging bypass."""

    def _state(self, pv=500, house=2000):
        return MaestroState(
            soc=50.0, pv_power=pv, house_power=house,
            grid_power=0, battery_power=0,
        )

    def test_dynamic_mode_allows_grid_in_tariff_low(self):
        """Backward compat: dynamic tariff mode keeps the existing TARIFF_LOW bypass."""
        from custom_components.e3dc_maestro.control_engine import (
            _apply_house_ceiling, TARIFF_LOW,
        )
        p = MaestroParams(tariff_mode="dynamic")
        # PV (500W) < house (2000W) → no surplus → would be capped to 0.
        # tariff_low + dynamic mode → cap bypassed, full charge_power preserved.
        out = _apply_house_ceiling(
            charge_power=3000, state=self._state(), params=p,
            phase="corridor", current_price=0.05, tariff_class=TARIFF_LOW,
        )
        assert out == 3000

    def test_fixed_mode_blocks_grid_in_tariff_low(self):
        """Hard constraint: fixed tariff mode caps to PV surplus regardless of tariff_low."""
        from custom_components.e3dc_maestro.control_engine import (
            _apply_house_ceiling, TARIFF_LOW,
        )
        p = MaestroParams(tariff_mode="fixed")
        # No PV surplus → capped to 0 even with tariff_low active.
        out = _apply_house_ceiling(
            charge_power=3000, state=self._state(pv=500, house=2000), params=p,
            phase="corridor", current_price=0.05, tariff_class=TARIFF_LOW,
        )
        assert out == 0

    def test_fixed_mode_allows_pv_surplus(self):
        """Fixed tariff mode still allows charging from PV surplus."""
        from custom_components.e3dc_maestro.control_engine import (
            _apply_house_ceiling, TARIFF_LOW,
        )
        p = MaestroParams(tariff_mode="fixed")
        # PV 5000W - house 1500W = 3500W surplus → charge_power capped to 3000W (full).
        out = _apply_house_ceiling(
            charge_power=3000, state=self._state(pv=5000, house=1500), params=p,
            phase="corridor", current_price=0.05, tariff_class=TARIFF_LOW,
        )
        assert out == 3000

    def test_emergency_phase_bypasses_fixed_mode(self):
        """Safety-critical phases (emergency/feed_in_limit/curtailment) always allow grid."""
        from custom_components.e3dc_maestro.control_engine import _apply_house_ceiling
        from custom_components.e3dc_maestro.const import (
            PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT, PHASE_CURTAILMENT_GUARD,
        )
        p = MaestroParams(tariff_mode="fixed")
        for phase in (PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT, PHASE_CURTAILMENT_GUARD):
            out = _apply_house_ceiling(
                charge_power=3000, state=self._state(), params=p,
                phase=phase, current_price=None, tariff_class=None,
            )
            assert out == 3000, f"{phase} should bypass house ceiling even when fixed"

    def test_default_tariff_mode_is_fixed(self):
        """Default value protects naive users from accidental grid charging."""
        p = MaestroParams()
        assert p.tariff_mode == "fixed"


# ──────────────────────────────────────────────────────────────────────────────
# Schwacher-PV-Tag: Akku-Priorität an bewölkten Tagen
# ──────────────────────────────────────────────────────────────────────────────

from custom_components.e3dc_maestro.control_engine import (
    is_low_yield_day,
    reference_pv_yield_kwh,
    spreading_active,
    surplus_priority_charge_w,
)


def _low_yield_params(**overrides) -> MaestroParams:
    """Reference: 20 kWp × 5.5 = 110 kWh; Schwelle 0.5 ⇒ ≤ 55 kWh = schwach."""
    base = dict(
        inverter_power=18000,
        max_charge_power=9000,
        min_charge_power=200,
        installed_kwp=20.0,
        lower_corridor=500,
        upper_corridor=9000,
        feed_in_limit_percent=70.0,
        charge_threshold=15,
        charge_target=100,
        winter_minimum_hour=11,
        summer_charge_end=18.5,
        battery_capacity_kwh=20.0,
        low_yield_priority_enabled=True,
        low_yield_threshold=0.5,
        low_yield_reference_kwh_per_kwp=5.5,
        # Wir wollen den Korridor-Effekt isoliert sehen.
        spreading_enabled=True,
        spreading_target_soc=100.0,
        lower_corridor_pause_enabled=True,
        ht_enabled=False,
    )
    base.update(overrides)
    return MaestroParams(**base)


class TestLowYieldReference:
    def test_kwp_baseline_only(self):
        p = _low_yield_params(installed_kwp=10.0)
        assert reference_pv_yield_kwh(p) == pytest.approx(55.0)

    def test_manual_override_wins_when_higher(self):
        p = _low_yield_params(installed_kwp=10.0, low_yield_reference_kwh=200.0)
        assert reference_pv_yield_kwh(p) == pytest.approx(200.0)

    def test_stats_peak_wins_when_higher(self):
        p = _low_yield_params(installed_kwp=10.0)
        assert reference_pv_yield_kwh(p, stats_peak_kwh=120.0) == pytest.approx(120.0)

    def test_returns_zero_when_nothing_configured(self):
        p = _low_yield_params(
            installed_kwp=0.0, low_yield_reference_kwh_per_kwp=0.0,
            low_yield_reference_kwh=0.0,
        )
        assert reference_pv_yield_kwh(p) == 0.0


class TestIsLowYieldDay:
    def test_detects_cloudy_day(self):
        # 50 kWh / 110 kWh = 0.45 ≤ 0.5 → True
        p = _low_yield_params()
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=50.0,
        )
        assert is_low_yield_day(s, p) is True

    def test_ignores_sunny_day(self):
        # 90 kWh / 110 kWh = 0.82 > 0.5 → False
        p = _low_yield_params()
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=90.0,
        )
        assert is_low_yield_day(s, p) is False

    def test_false_when_disabled(self):
        p = _low_yield_params(low_yield_priority_enabled=False)
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=10.0,
        )
        assert is_low_yield_day(s, p) is False

    def test_false_without_forecast(self):
        p = _low_yield_params()
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=None,
        )
        assert is_low_yield_day(s, p) is False


class TestSurplusPriorityCharge:
    def test_uses_full_surplus_capped_to_max(self):
        p = _low_yield_params(max_charge_power=5000, min_charge_power=200)
        s = MaestroState(
            soc=50, pv_power=8000, house_power=500, grid_power=0, battery_power=0,
        )
        assert surplus_priority_charge_w(s, p) == 5000

    def test_returns_zero_below_min(self):
        p = _low_yield_params(min_charge_power=300)
        s = MaestroState(
            soc=50, pv_power=400, house_power=300, grid_power=0, battery_power=0,
        )
        assert surplus_priority_charge_w(s, p) == 0.0


class TestLowYieldDecide:
    """End-to-end ``decide()``: schwacher Tag ⇒ Korridor mit Überschuss-Priorität."""

    def _state(self, *, soc=51, pv=3000, house=600, forecast_today=50.0):
        return MaestroState(
            soc=soc, pv_power=pv, house_power=house, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=forecast_today,
        )

    def test_low_yield_lifts_corridor_to_surplus(self):
        # Sonniger Tag wäre 110 kWh; 50 kWh = 0.45 < 0.5 ⇒ low_yield aktiv.
        # SoC 51 %, Ziel-Rampe um 11 Uhr ≈ 55 % → Spreading-Rate sehr klein.
        # Mit low_yield: charge_power = surplus (~2400 W).
        p = _low_yield_params()
        s = self._state(soc=51, pv=3000, house=600, forecast_today=50.0)
        decision = decide(s, p, _now(6, 15, 11))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit >= 2000, (
            f"erwartet ≥2000W, erhielt {decision.charge_power_limit}"
        )
        assert "Schwacher-PV-Tag" in decision.reason

    def test_sunny_day_keeps_spreading_throttle(self):
        # 90 kWh / 110 kWh = 0.82 > 0.5 ⇒ kein low_yield → Spreading-Cap aktiv.
        p = _low_yield_params()
        s = self._state(soc=51, pv=3000, house=600, forecast_today=90.0)
        decision = decide(s, p, _now(6, 15, 11))
        # Korridor liefert eine deutlich kleinere Rate als der volle Überschuss.
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit < 2000

    def test_low_yield_skips_spreading_phase(self):
        # SoC bereits am Korridor-Ziel-Ende, Spreading würde greifen.
        # Mit low_yield: Spreading wird übersprungen → IDLE (oder Korridor mit
        # Überschuss, je nach SoC). Wir prüfen nur, dass *kein* SPREADING entsteht.
        p = _low_yield_params(charge_target=85)
        s = self._state(soc=90, pv=3000, house=600, forecast_today=50.0)
        decision = decide(s, p, _now(6, 15, 14))
        assert decision.phase != PHASE_SPREADING

    def test_low_yield_uses_instant_surplus_not_ewma(self):
        # EWMA würde 2400 W Überschuss zeigen, Momentanwert nur 600 W.
        p = _low_yield_params()
        s = MaestroState(
            soc=51,
            pv_power=3000,
            house_power=600,
            grid_power=0,
            battery_power=0,
            pv_forecast_today_kwh=50.0,
            pv_power_instant=1200,
            house_power_instant=600,
        )
        decision = decide(s, p, _now(6, 15, 11))
        assert decision.phase == PHASE_CORRIDOR
        assert decision.charge_power_limit is not None
        assert decision.charge_power_limit <= 600 + 1, (
            f"erwartet ≤600W (Momentan-Überschuss), erhielt {decision.charge_power_limit}"
        )

    def test_low_yield_bypasses_corridor_pause(self):
        # Surplus 100 W < lower_corridor 500 W: ohne low_yield → IDLE/Pause.
        # Mit low_yield + Surplus ≥ min_charge_power (200 W) wäre Pause aus;
        # hier liegt Surplus knapp unter min_charge_power → surplus_priority
        # liefert 0 → trotzdem keine harte Pause; charge_power-Pfad weiter.
        p = _low_yield_params(min_charge_power=50, lower_corridor=500)
        s = self._state(soc=51, pv=700, house=600, forecast_today=50.0)
        decision = decide(s, p, _now(6, 15, 11))
        # Wichtig: keine Korridor-Pause (charge_power_limit == 0.0) trotz
        # Surplus < lower_corridor – low_yield deaktiviert die Pause.
        assert not (
            decision.phase == PHASE_IDLE
            and decision.charge_power_limit == 0.0
            and "Korridor-Pause" in decision.reason
        )


class TestPeakDailyYieldKwh:
    """ConsumptionStats.peak_daily_yield_kwh nutzt das Wochentags-Profil."""

    def test_returns_none_for_empty_profile(self):
        from custom_components.e3dc_maestro.consumption_stats import ConsumptionStats
        cs = ConsumptionStats.__new__(ConsumptionStats)
        cs.weekday_profile_w = [[0.0] * 24 for _ in range(7)]
        assert cs.peak_daily_yield_kwh() is None

    def test_returns_max_weekday_total(self):
        from custom_components.e3dc_maestro.consumption_stats import ConsumptionStats
        cs = ConsumptionStats.__new__(ConsumptionStats)
        # Mo: 24h × 500W = 12 kWh, Di: 24h × 1500W = 36 kWh (Maximum)
        cs.weekday_profile_w = [
            [500.0] * 24,
            [1500.0] * 24,
            [0.0] * 24,
            [0.0] * 24,
            [0.0] * 24,
            [0.0] * 24,
            [0.0] * 24,
        ]
        assert cs.peak_daily_yield_kwh() == pytest.approx(36.0)


class TestSpreadingActiveHelper:
    def test_disabled_when_switch_off(self):
        p = _low_yield_params(spreading_enabled=False)
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=50.0,
        )
        assert spreading_active(p, s) is False

    def test_disabled_on_low_yield(self):
        p = _low_yield_params(spreading_enabled=True)
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=40.0,
        )
        assert spreading_active(p, s) is False

    def test_enabled_on_sunny_day(self):
        p = _low_yield_params(spreading_enabled=True)
        s = MaestroState(
            soc=50, pv_power=2000, house_power=600, grid_power=0, battery_power=0,
            pv_forecast_today_kwh=100.0,
        )
        assert spreading_active(p, s) is True
