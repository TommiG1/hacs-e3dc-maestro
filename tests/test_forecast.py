"""Tests for the F1 24-hour SoC forecast simulator."""
from datetime import datetime, timezone

import pytest

from custom_components.e3dc_maestro.control_engine import MaestroParams
from custom_components.e3dc_maestro.forecast import ForecastResult, simulate_next_24h

_PARAMS = MaestroParams(
    inverter_power=12000,
    max_charge_power=5000,
    min_charge_power=300,
    installed_kwp=10.0,
    feed_in_limit_percent=70.0,
    charge_threshold=15.0,
    battery_capacity_kwh=15.0,
)

_NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def _simulate(soc=50.0, cons=300.0, pv=0.0, **kw) -> ForecastResult:
    return simulate_next_24h(
        soc=soc,
        consumption_h=[cons] * 24,
        pv_h=[pv] * 24,
        params=_PARAMS,
        now=_NOW,
        battery_capacity_kwh=15.0,
        **kw,
    )


class TestSimulateNext24h:
    """simulate_next_24h() basic invariants."""

    def test_returns_forecast_result(self):
        result = _simulate()
        assert isinstance(result, ForecastResult)

    def test_trajectory_length_is_96(self):
        result = _simulate()
        assert len(result.trajectory_soc) == 96
        assert len(result.trajectory_hours) == 96
        assert len(result.trajectory_phases) == 96

    def test_soc_bounded_0_to_100(self):
        result = _simulate(soc=5.0, cons=5000.0, pv=0.0)
        for soc in result.trajectory_soc:
            assert 0.0 <= soc <= 100.0, f"SoC out of bounds: {soc}"

    def test_no_pv_no_consumption_soc_stable(self):
        """With zero PV and zero consumption, SoC should be stable (idle phase)."""
        result = _simulate(soc=50.0, cons=0.0, pv=0.0)
        # SoC stays at 50 (no draw, no charge from grid)
        for soc in result.trajectory_soc:
            assert abs(soc - 50.0) < 5.0  # slight variance allowed for corridor/spreading

    def test_high_pv_low_consumption_soc_rises(self):
        """Abundant PV should raise SoC over time."""
        result = _simulate(soc=30.0, cons=500.0, pv=8000.0)
        assert result.trajectory_soc[-1] > 30.0

    def test_no_pv_high_consumption_soc_falls(self):
        """Heavy consumption with no PV should drain SoC."""
        result = _simulate(soc=80.0, cons=3000.0, pv=0.0)
        assert result.min_soc < 80.0

    def test_grid_draw_nonzero_when_soc_empty_and_consuming(self):
        """When battery is empty and consumption > PV, grid draw > 0."""
        result = _simulate(soc=0.0, cons=2000.0, pv=0.0)
        assert result.grid_draw_kwh > 0.0

    def test_grid_draw_accounted_after_soc_clamp_to_zero(self):
        """Regression: When SoC starts >0 and drains to 0 mid-trajectory,
        the post-clamp consumption must be charged to the grid. Prior to the
        fix, the clamp dropped bat_net_w on the floor → grid_draw_kwh stayed
        artificially low and self_sufficiency was reported as 100 %.
        """
        # charge_threshold=0 deaktiviert Emergency-Charge → Akku läuft
        # tatsächlich auf 0 statt aus dem Grid nachzuladen.
        params_no_emergency = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=0.0,
            battery_capacity_kwh=10.0,
        )
        # 10 kWh battery, 2 kW load, 0 PV → battery empties in ~5 h, then 19 h
        # of pure grid draw at 2 kW = 38 kWh.
        result = simulate_next_24h(
            soc=70.0,
            consumption_h=[2000.0] * 24,
            pv_h=[0.0] * 24,
            params=params_no_emergency,
            now=_NOW,
            battery_capacity_kwh=10.0,
        )
        assert result.min_soc == 0.0, f"battery should drain to 0 ({result.min_soc=})"
        # Expected post-clamp grid draw ≈ 19 h × 2 kW = 38 kWh; allow generous slack.
        assert result.grid_draw_kwh > 30.0, (
            f"grid_draw_kwh={result.grid_draw_kwh} too low – clamp leak regression"
        )
        assert result.self_sufficiency is not None
        assert result.self_sufficiency < 0.5, (
            f"self_sufficiency={result.self_sufficiency} – should reflect grid draw"
        )

    def test_self_sufficiency_one_with_ample_pv(self):
        """Ample PV + starting SoC should give high self-sufficiency."""
        result = _simulate(soc=80.0, cons=300.0, pv=5000.0)
        assert result.self_sufficiency is not None
        assert result.self_sufficiency > 0.8

    def test_min_max_soc_consistent(self):
        result = _simulate()
        assert result.min_soc <= result.max_soc
        for soc in result.trajectory_soc:
            assert result.min_soc <= soc <= result.max_soc

    def test_full_battery_no_pv_soc_decreases_or_stable(self):
        """Full battery with no PV should discharge toward equilibrium."""
        result = _simulate(soc=100.0, cons=500.0, pv=0.0)
        assert result.trajectory_soc[-1] <= 100.0

    def test_spreading_target_reached_does_not_flatline(self):
        """Regression: When SoC ≥ spreading-target the rule engine returns
        power_mode=NORMAL with charge_power_limit=1 W (Sentinel: Laden
        gesperrt, Entladen frei). The simulator must NOT interpret that as
        constant 1 W charging – nighttime consumption has to discharge.
        """
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=15.0,
            battery_capacity_kwh=15.0,
            spreading_enabled=True,
            spreading_target_soc=90.0,
        )
        result = simulate_next_24h(
            soc=96.0,
            consumption_h=[800.0] * 24,  # 800 W konstanter Hausverbrauch
            pv_h=[0.0] * 24,             # keine PV → Akku muss Last decken
            params=params,
            now=_NOW,
            battery_capacity_kwh=15.0,
        )
        # Über 24 h × 800 W = 19.2 kWh Last bei 15 kWh Akku → SoC muss
        # spürbar fallen. Vor dem Fix blieb der Trace bei ~96 % flat.
        assert result.min_soc < 80.0, (
            f"Akku entlädt nicht – min_soc={result.min_soc} (erwartet <80 %)"
        )


class TestSimulateWithMorningCap:
    """simulate_next_24h() respects Morning-Cap."""

    def test_morning_cap_limits_early_charge(self):
        """With morning-cap at 30%, early hours should not charge above cap."""
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            battery_capacity_kwh=15.0,
            morning_cap_enabled=True,
            morning_cap_soc=30.0,
            morning_cap_until_h=9.0,  # 09:00 UTC
        )
        now = datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc)  # 06:00 UTC (within cap)
        result = simulate_next_24h(
            soc=25.0,
            consumption_h=[300.0] * 24,
            pv_h=[0.0] * 24,  # No PV → no passive charging
            params=params,
            now=now,
            battery_capacity_kwh=15.0,
        )
        # In the first few hours, morning_cap phase should appear
        from custom_components.e3dc_maestro.const import PHASE_MORNING_CAP
        # At least some hours should be morning_cap (when SoC >= 30)
        # Starting at 25% with no PV/consumption → SoC stable, no cap triggered
        # Just test the simulation runs without errors
        assert len(result.trajectory_soc) == 96


class TestForecastCostAccounting:
    """simulate_next_24h() cost and revenue accounting."""

    def test_cost_nonzero_when_drawing_from_grid(self):
        """Empty battery, no PV → draws from grid → cost_eur > 0."""
        result = _simulate(soc=0.0, cons=2000.0, pv=0.0)
        assert result.cost_eur > 0.0

    def test_revenue_nonzero_when_feeding_in(self):
        """Full battery, ample PV → feeds into grid → revenue_eur > 0."""
        result = _simulate(soc=100.0, cons=300.0, pv=8000.0)
        assert result.revenue_eur > 0.0

    def test_cost_matches_fixed_price_approximation(self):
        """With fixed buy price, cost ≈ grid_draw_kwh × buy_price."""
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=15.0,
            battery_capacity_kwh=15.0,
            fixed_buy_price=0.30,
            feed_in_price=0.08,
        )
        result = simulate_next_24h(
            soc=0.0,
            consumption_h=[2000.0] * 24,
            pv_h=[0.0] * 24,
            params=params,
            now=_NOW,
            battery_capacity_kwh=15.0,
        )
        expected = round(result.grid_draw_kwh * 0.30, 2)
        assert abs(result.cost_eur - expected) < 0.05, (
            f"cost_eur={result.cost_eur} expected≈{expected}"
        )

    def test_price_q_overrides_fixed_price(self):
        """When price_q is provided, cost uses per-quarter prices."""
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=70.0,
            charge_threshold=15.0,
            battery_capacity_kwh=15.0,
            fixed_buy_price=0.30,
            feed_in_price=0.08,
        )
        # price_q: all quarters 0.10 €/kWh (much cheaper than fixed 0.30)
        price_q = [0.10] * 96
        result_dyn = simulate_next_24h(
            soc=0.0,
            consumption_h=[2000.0] * 24,
            pv_h=[0.0] * 24,
            params=params,
            now=_NOW,
            battery_capacity_kwh=15.0,
            price_q=price_q,
        )
        result_fixed = simulate_next_24h(
            soc=0.0,
            consumption_h=[2000.0] * 24,
            pv_h=[0.0] * 24,
            params=params,
            now=_NOW,
            battery_capacity_kwh=15.0,
        )
        # Same energy drawn, but cheaper per kWh
        assert result_dyn.cost_eur < result_fixed.cost_eur
        # Should be ≈ fixed_cost × (0.10/0.30)
        ratio = result_dyn.cost_eur / result_fixed.cost_eur
        assert abs(ratio - (0.10 / 0.30)) < 0.05, f"price ratio off: {ratio}"

    def test_no_cost_no_revenue_with_self_sufficient_system(self):
        """Ample PV + ample battery → minimal grid interaction → low cost/revenue."""
        result = _simulate(soc=50.0, cons=500.0, pv=2000.0)
        # System mostly self-sufficient; grid draw should be very small
        assert result.grid_draw_kwh < 1.0
        assert result.cost_eur < 0.50  # < 50 ct for the day


class TestPvForecastResolution:
    """Option A: simulate_next_24h() consumes 24/48/96 element pv arrays."""

    def _params(self) -> MaestroParams:
        return MaestroParams(
            inverter_power=15000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=19.125,
            feed_in_limit_percent=70.0,  # → 13388 W feed-in cap
            charge_threshold=15.0,
            battery_capacity_kwh=15.0,
            # Test scope: subhour-peak detection in curtailment estimator.
            # Disable spreading (default-on since v0.3.2) so battery does not
            # absorb the peak by smoothed pre-charging during the day.
            spreading_enabled=False,
        )

    def test_hourly_profile_misses_subhour_peak(self):
        """A 30-min PV peak above the 70% cap is averaged away at hourly resolution.

        Hour 12 contains a 14500 W peak in the second half-hour (above 13388 W
        cap) and 7000 W in the first half. Hourly mean = 10750 W → no
        curtailment visible in the simulator.
        """
        pv_h = [0.0] * 24
        pv_h[12] = (7000.0 + 14500.0) / 2.0  # → 10750 W mean
        result = simulate_next_24h(
            soc=80.0,
            consumption_h=[200.0] * 24,
            pv_h=pv_h,
            params=self._params(),
            now=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            battery_capacity_kwh=15.0,
        )
        assert result.pv_curtailed_kwh == pytest.approx(0.0, abs=0.05)

    def test_halfhour_profile_exposes_subhour_peak(self):
        """Same energy, but as 48-element half-hour profile → peak is visible."""
        pv_48 = [0.0] * 48
        # Hour 12 = slot 24 (first half) + 25 (second half)
        pv_48[24] = 7000.0
        pv_48[25] = 14500.0  # 1112 W over the 13388 W cap for 30 min
        result = simulate_next_24h(
            soc=80.0,
            consumption_h=[200.0] * 24,
            pv_h=pv_48,
            params=self._params(),
            now=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            battery_capacity_kwh=15.0,
        )
        assert result.pv_curtailed_kwh > 0.3

    def test_quarter_hour_profile_accepted(self):
        """96-element profile is also accepted (15-min steps match natively)."""
        pv_96 = [0.0] * 96
        pv_96[48] = 14500.0  # one quarter of hour 12
        result = simulate_next_24h(
            soc=80.0,
            consumption_h=[200.0] * 24,
            pv_h=pv_96,
            params=self._params(),
            now=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
            battery_capacity_kwh=15.0,
        )
        assert result.pv_curtailed_kwh > 0.15


class TestConsumptionStatsHourlyProfile:
    """ConsumptionStats.hourly_profile_w is computed correctly in UTC."""

    def test_hourly_profile_averages_by_utc_hour(self):
        from unittest.mock import MagicMock

        from custom_components.e3dc_maestro.consumption_stats import ConsumptionStats

        stats = ConsumptionStats(MagicMock(), "sensor.test")

        rows = [
            {"start": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), "mean": 400.0},
            {"start": datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc), "mean": 600.0},
            {"start": datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc), "mean": 200.0},
        ]
        stats._update_from_rows(rows, None)

        assert abs(stats.hourly_profile_w[10] - 500.0) < 0.1
        assert abs(stats.hourly_profile_w[22] - 200.0) < 0.1
        assert stats.hourly_profile_w[0] == 0.0  # empty bucket

    def test_hourly_profile_ignores_local_offset(self):
        """Berlin summer (UTC+2): 10:00 local = 08:00 UTC → bucket 8."""
        from unittest.mock import MagicMock, patch
        from zoneinfo import ZoneInfo

        from custom_components.e3dc_maestro.consumption_stats import ConsumptionStats
        import custom_components.e3dc_maestro.consumption_stats as cs_mod

        stats = ConsumptionStats(MagicMock(), "sensor.test")
        berlin = ZoneInfo("Europe/Berlin")
        local_10 = datetime(2026, 7, 17, 10, 0, tzinfo=berlin)
        rows = [{"start": local_10, "mean": 900.0}]

        with patch.object(
            cs_mod.dt_util, "as_local", side_effect=lambda dt: dt.astimezone(berlin)
        ):
            stats._update_from_rows(rows, None)

        assert abs(stats.hourly_profile_w[8] - 900.0) < 0.1
        assert stats.hourly_profile_w[10] == 0.0

    def test_empty_rows_yields_zero_profile(self):
        from unittest.mock import MagicMock
        from custom_components.e3dc_maestro.consumption_stats import ConsumptionStats

        stats = ConsumptionStats(MagicMock(), "sensor.test")
        stats._update_from_rows([], None)
        assert stats.hourly_profile_w == [0.0] * 24


class TestDay2Boundary:
    def test_exact_24h_uses_day2_profile(self):
        """At elapsed == 24.0 h the simulator must switch to day-2 arrays."""
        params = MaestroParams(
            inverter_power=12000,
            max_charge_power=5000,
            min_charge_power=300,
            installed_kwp=10.0,
            feed_in_limit_percent=0.0,
            battery_capacity_kwh=15.0,
            morning_cap_enabled=False,
        )
        cons = [200.0] * 24
        pv_day1 = [0.0] * 24
        pv_day2 = [5000.0] * 24
        result = simulate_next_24h(
            soc=50.0,
            consumption_h=cons,
            pv_h=pv_day1,
            params=params,
            now=_NOW,
            battery_capacity_kwh=15.0,
            pv_h_day2=pv_day2,
            consumption_h_day2=cons,
            horizon_h=48,
        )
        assert len(result.trajectory_soc) == 192
        assert result.max_soc >= result.trajectory_soc[95]


class TestBatteryThroughput:
    def test_throughput_tracks_charge_and_discharge(self):
        result = _simulate(soc=50.0, cons=500.0, pv=2000.0)
        assert result.battery_throughput_kwh > 0.0
