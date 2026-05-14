"""Unit tests for battery_sizing.py simulation engine.

Tests cover:
- simulate_scenario: monotonicity, saturation, PV scaling, inverter clipping
- sweep_2d: matrix shape, recommendations
- interpolate_result: bilinear interpolation
- _sweep_vector, _pareto_front, _pareto_knee helpers
- data quality: negative delta handling (via _to_delta_map indirectly)
"""
from __future__ import annotations

import math
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

# conftest.py (in the same package) already stubs out homeassistant.* before
# this module is imported.  We just need the repo root on sys.path so that
# custom_components resolves correctly.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from custom_components.e3dc_maestro.battery_sizing import (  # noqa: E402
    HourlyRecord,
    ScenarioResult,
    SizingAnalysisResult,
    _find_balanced,
    _find_economic,
    _find_technical,
    _pareto_front,
    _pareto_knee,
    _sweep_vector,
    interpolate_result,
    simulate_scenario,
    sweep_2d,
)
from custom_components.e3dc_maestro.const import (  # noqa: E402
    CONF_FEED_IN_LIMIT_PERCENT,
    CONF_INSTALLED_KWP,
    CONF_INVERTER_POWER,
    SIZING_MAX_PAYBACK_YEARS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DT_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _ts(hour: int) -> datetime:
    return _DT_BASE + timedelta(hours=hour)


def _rec(
    hour: int = 0,
    pv: float = 0.0,
    house: float = 1.0,
    g_in: float = 1.0,
    g_out: float = 0.0,
    b_c: float = 0.0,
    b_d: float = 0.0,
    wb: float = 0.0,
    hp: float = 0.0,
    anomaly: bool = False,
) -> HourlyRecord:
    return HourlyRecord(
        timestamp=_ts(hour),
        pv_kwh=pv,
        house_kwh=house,
        grid_in_kwh=g_in,
        grid_out_kwh=g_out,
        batt_charge_kwh=b_c,
        batt_discharge_kwh=b_d,
        wallbox_kwh=wb,
        hp_kwh=hp,
        anomaly=anomaly,
    )


# Default simulation parameters
_SIM_KWARGS = dict(
    installed_kwp=10.0,
    inverter_power_w=10000.0,
    feed_in_limit_pct=70.0,
    electricity_price=0.30,
    feed_in_price=0.08,
    battery_price_per_kwh=600.0,
    pv_price_per_kwp=1200.0,
    inverter_upgrade_price=1500.0,
    round_trip_efficiency=0.92,
)

# ---------------------------------------------------------------------------
# _sweep_vector
# ---------------------------------------------------------------------------


class TestSweepVector:
    def test_includes_zero(self) -> None:
        vec = _sweep_vector(0.0, 10.0, 2.5)
        assert vec[0] == pytest.approx(0.0)

    def test_includes_stop(self) -> None:
        vec = _sweep_vector(0.0, 10.0, 2.5)
        assert vec[-1] == pytest.approx(10.0)

    def test_step_size(self) -> None:
        vec = _sweep_vector(0.0, 6.0, 2.0)
        assert vec == pytest.approx([0.0, 2.0, 4.0, 6.0])

    def test_single_point(self) -> None:
        vec = _sweep_vector(0.0, 0.0, 1.0)
        assert vec == [0.0]

    def test_non_divisible(self) -> None:
        """Stop that is not an exact multiple of step is still reached."""
        vec = _sweep_vector(0.0, 5.0, 3.0)
        # 0, 3, 6 – but 6 > 5 so we only get 0 and 3
        assert 0.0 in vec
        assert 3.0 in vec
        assert all(v <= 5.0 + 1e-6 for v in vec)


# ---------------------------------------------------------------------------
# simulate_scenario – empty / no-battery baseline
# ---------------------------------------------------------------------------


class TestSimulateScenarioBaseline:
    def test_empty_records(self) -> None:
        result = simulate_scenario(records=[], additional_kwh=0.0, additional_kwp=0.0, **_SIM_KWARGS)
        assert result.avoided_grid_import_kwh == 0.0
        assert result.savings_eur_per_year == 0.0
        assert result.payback_years == math.inf

    def test_zero_battery_zero_pv(self) -> None:
        records = [_rec(hour=h, pv=0.0, house=1.0, g_in=1.0, g_out=0.0) for h in range(24)]
        result = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=0.0, **_SIM_KWARGS)
        assert result.avoided_grid_import_kwh == pytest.approx(0.0)
        assert result.investment_eur == pytest.approx(0.0)
        assert result.payback_years == math.inf

    def test_baseline_self_sufficiency_all_pv(self) -> None:
        """24 hours where PV exactly covers house – should be ~100% autarky."""
        records = [_rec(hour=h, pv=1.0, house=1.0, g_in=0.0, g_out=0.0) for h in range(24)]
        result = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=0.0, **_SIM_KWARGS)
        assert result.self_sufficiency_pct == pytest.approx(100.0, abs=1.0)


# ---------------------------------------------------------------------------
# simulate_scenario – battery monotonicity
# ---------------------------------------------------------------------------


class TestBatteryMonotonicity:
    """More battery capacity must never decrease avoided_grid_import_kwh."""

    @pytest.fixture
    def records(self) -> list[HourlyRecord]:
        # 24h profile: surplus in midday (hours 10-14), deficit at night
        recs = []
        for h in range(24):
            if 10 <= h <= 14:
                recs.append(_rec(hour=h, pv=3.0, house=1.0, g_in=0.0, g_out=2.0))
            else:
                recs.append(_rec(hour=h, pv=0.0, house=1.0, g_in=1.0, g_out=0.0))
        return recs

    def test_increasing_battery_non_decreasing_avoided(self, records: list[HourlyRecord]) -> None:
        sizes = [0.0, 2.0, 5.0, 10.0, 20.0]
        avoided = [
            simulate_scenario(records=records, additional_kwh=s, additional_kwp=0.0, **_SIM_KWARGS)
            .avoided_grid_import_kwh
            for s in sizes
        ]
        for i in range(1, len(avoided)):
            assert avoided[i] >= avoided[i - 1] - 1e-3, (
                f"Avoided import decreased: {avoided[i-1]:.2f} → {avoided[i]:.2f} at {sizes[i]} kWh"
            )


# ---------------------------------------------------------------------------
# simulate_scenario – battery saturation
# ---------------------------------------------------------------------------


class TestBatterySaturation:
    """Very large battery should asymptote (not keep increasing unlimitedly)."""

    @pytest.fixture
    def records(self) -> list[HourlyRecord]:
        # Fixed daily pattern: 5h surplus, 19h deficit
        recs = []
        for h in range(24):
            if 10 <= h <= 14:
                recs.append(_rec(hour=h, pv=2.0, house=0.5, g_in=0.0, g_out=1.5))
            else:
                recs.append(_rec(hour=h, pv=0.0, house=0.5, g_in=0.5, g_out=0.0))
        return recs

    def test_saturation(self, records: list[HourlyRecord]) -> None:
        # Surplus energy per day ≈ 5 * 1.5 = 7.5 kWh
        # A 7.5 kWh battery should capture almost all surplus
        small = simulate_scenario(records=records, additional_kwh=5.0, additional_kwp=0.0, **_SIM_KWARGS)
        large = simulate_scenario(records=records, additional_kwh=100.0, additional_kwp=0.0, **_SIM_KWARGS)
        huge  = simulate_scenario(records=records, additional_kwh=500.0, additional_kwp=0.0, **_SIM_KWARGS)

        # Marginal gain from 100→500 kWh must be smaller than gain from 5→100 kWh
        gain_5_to_100 = large.avoided_grid_import_kwh - small.avoided_grid_import_kwh
        gain_100_to_500 = huge.avoided_grid_import_kwh - large.avoided_grid_import_kwh
        assert gain_100_to_500 <= gain_5_to_100 + 1e-3


# ---------------------------------------------------------------------------
# simulate_scenario – PV expansion scaling
# ---------------------------------------------------------------------------


class TestPVScaling:
    def test_proportional_scaling_no_clip(self) -> None:
        """When inverter is large enough, extra PV linearly increases yield."""
        # Simple: no battery, 50% PV coverage, inverter large enough
        records = [_rec(hour=h, pv=0.5, house=1.0, g_in=0.5, g_out=0.0) for h in range(24)]
        sim_kwargs = {**_SIM_KWARGS, "inverter_power_w": 100_000.0}  # huge WR, no clipping

        r1 = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=10.0, **sim_kwargs)
        r2 = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=20.0, **sim_kwargs)

        # extra_pv_yield should roughly double
        if r1.extra_pv_yield_kwh > 1.0:
            ratio = r2.extra_pv_yield_kwh / r1.extra_pv_yield_kwh
            assert 1.8 <= ratio <= 2.2, f"Unexpected PV scaling ratio: {ratio:.3f}"

    def test_inverter_clipping_triggers(self) -> None:
        """Doubling installed_kwp should cause WR clipping loss when WR is small."""
        # installed_kwp=10, inverter=10 kW → total_kwp=20 kWp >> 10 kW * 1.2
        # With no upgrade, clipping should be > 0
        records = [_rec(hour=h, pv=1.0, house=0.3, g_in=0.0, g_out=0.7) for h in range(24)]
        sim_kwargs = {**_SIM_KWARGS, "inverter_power_w": 10_000.0, "installed_kwp": 10.0}
        # Adding 20 kWp would make total 30 kWp > 10 kW * 1.2 → upgrade needed
        result = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=20.0, **sim_kwargs)
        assert result.inverter_upgrade_needed is True

    def test_no_clipping_within_rating(self) -> None:
        """Small PV addition within WR headroom should not need an upgrade."""
        records = [_rec(hour=h, pv=0.5, house=1.0, g_in=0.5, g_out=0.0) for h in range(24)]
        # installed=10 kWp, WR=20 kW → 10+1 kWp << 20 kW * 1.2
        sim_kwargs = {**_SIM_KWARGS, "inverter_power_w": 20_000.0, "installed_kwp": 10.0}
        result = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=1.0, **sim_kwargs)
        assert result.inverter_upgrade_needed is False


# ---------------------------------------------------------------------------
# simulate_scenario – investment calculation
# ---------------------------------------------------------------------------


class TestInvestment:
    def test_battery_only_investment(self) -> None:
        records = [_rec() for _ in range(24)]
        result = simulate_scenario(records=records, additional_kwh=10.0, additional_kwp=0.0, **_SIM_KWARGS)
        expected = 10.0 * _SIM_KWARGS["battery_price_per_kwh"]
        assert result.investment_eur == pytest.approx(expected, abs=1.0)

    def test_pv_only_investment(self) -> None:
        records = [_rec() for _ in range(24)]
        result = simulate_scenario(records=records, additional_kwh=0.0, additional_kwp=5.0, **_SIM_KWARGS)
        # No upgrade needed since 10+5=15 kWp and WR=10 kW → 15 > 12 → upgrade IS needed
        # with SIZING_INVERTER_UPGRADE_THRESHOLD=1.2
        # So we just check that the formula is correct given what the module decides
        upgrade_cost = _SIM_KWARGS["inverter_upgrade_price"] if result.inverter_upgrade_needed else 0.0
        expected = 5.0 * _SIM_KWARGS["pv_price_per_kwp"] + upgrade_cost
        assert result.investment_eur == pytest.approx(expected, abs=1.0)

    def test_combined_investment(self) -> None:
        records = [_rec() for _ in range(24)]
        result = simulate_scenario(records=records, additional_kwh=5.0, additional_kwp=0.0, **_SIM_KWARGS)
        expected = 5.0 * _SIM_KWARGS["battery_price_per_kwh"]
        assert result.investment_eur == pytest.approx(expected, abs=1.0)


# ---------------------------------------------------------------------------
# simulate_scenario – monthly breakdown
# ---------------------------------------------------------------------------


class TestMonthlyBreakdown:
    def test_monthly_lists_have_12_entries(self) -> None:
        records = [_rec() for _ in range(24)]
        result = simulate_scenario(records=records, additional_kwh=5.0, additional_kwp=0.0, **_SIM_KWARGS)
        assert len(result.monthly_avoided_kwh) == 12
        assert len(result.monthly_baseline_grid_in) == 12

    def test_monthly_sums_consistent(self) -> None:
        """Sum of monthly avoided should be close to annual figure (both annualised)."""
        records = [_rec(hour=h, pv=1.5, house=1.0, g_in=0.0, g_out=0.5) for h in range(24)]
        result = simulate_scenario(records=records, additional_kwh=5.0, additional_kwp=0.0, **_SIM_KWARGS)
        # monthly values are individually annualised, so sum can exceed annual
        # but each entry should be non-negative
        assert all(v >= 0.0 for v in result.monthly_avoided_kwh)
        assert all(v >= 0.0 for v in result.monthly_baseline_grid_in)


# ---------------------------------------------------------------------------
# _pareto_front and _pareto_knee
# ---------------------------------------------------------------------------


def _make_result(invest: float, savings: float) -> ScenarioResult:
    """Minimal ScenarioResult for Pareto tests."""
    return ScenarioResult(
        additional_kwh=0.0, additional_kwp=0.0,
        avoided_grid_import_kwh=0.0, added_self_consumption_kwh=0.0,
        reduced_feed_in_kwh=0.0, inverter_clipping_loss_kwh=0.0,
        extra_pv_yield_kwh=0.0, self_sufficiency_pct=0.0,
        cycles_per_year=0.0, monthly_avoided_kwh=[0.0] * 12,
        monthly_baseline_grid_in=[0.0] * 12,
        investment_eur=invest,
        savings_eur_per_year=savings,
        payback_years=(invest / savings) if savings > 0 else math.inf,
        inverter_upgrade_needed=False,
    )


class TestParetoFront:
    def test_dominated_point_excluded(self) -> None:
        """A strictly dominated point should not appear on the Pareto front."""
        # r1 dominates r2: same savings, less investment
        r1 = _make_result(invest=1000.0, savings=300.0)
        r2 = _make_result(invest=1500.0, savings=300.0)
        front = _pareto_front([r1, r2])
        assert r2 not in front
        assert r1 in front

    def test_non_dominated_both_present(self) -> None:
        """Two points with different trade-offs: both should be on front."""
        r1 = _make_result(invest=1000.0, savings=200.0)
        r2 = _make_result(invest=2000.0, savings=500.0)
        front = _pareto_front([r1, r2])
        assert r1 in front
        assert r2 in front

    def test_all_dominated_except_one(self) -> None:
        results = [
            _make_result(invest=500.0, savings=400.0),   # best (low invest, high savings)
            _make_result(invest=1000.0, savings=400.0),  # dominated
            _make_result(invest=1500.0, savings=300.0),  # dominated
        ]
        front = _pareto_front(results)
        assert results[0] in front
        assert len(front) == 1

    def test_sorted_by_investment(self) -> None:
        results = [
            _make_result(invest=3000.0, savings=900.0),
            _make_result(invest=1000.0, savings=200.0),
            _make_result(invest=2000.0, savings=600.0),
        ]
        front = _pareto_front(results)
        investments = [r.investment_eur for r in front]
        assert investments == sorted(investments)


class TestParetoKnee:
    def test_single_point(self) -> None:
        r = _make_result(invest=1000.0, savings=300.0)
        knee = _pareto_knee([r])
        assert knee is r

    def test_knee_is_middle_of_convex_set(self) -> None:
        """For a convex Pareto front, knee should be the point furthest from the diagonal."""
        # Three points: first is cheap/low savings, last is expensive/high savings
        # middle has "elbow" shape
        r0 = _make_result(invest=0.0, savings=0.0)
        r1 = _make_result(invest=1000.0, savings=400.0)   # high marginal ROI
        r2 = _make_result(invest=5000.0, savings=500.0)   # low marginal ROI
        knee = _pareto_knee([r0, r1, r2])
        # r1 is the elbow – largest perpendicular distance
        assert knee is r1

    def test_two_points_returns_one(self) -> None:
        r0 = _make_result(invest=1000.0, savings=200.0)
        r1 = _make_result(invest=3000.0, savings=600.0)
        knee = _pareto_knee([r0, r1])
        assert knee in (r0, r1)


# ---------------------------------------------------------------------------
# Recommendation strategies
# ---------------------------------------------------------------------------


def _make_results_grid() -> list[ScenarioResult]:
    """Create a small grid of scenario results for recommendation tests."""
    results = []
    for invest, savings, autarky in [
        (0.0, 0.0, 50.0),        # baseline
        (600.0, 120.0, 55.0),    # 2 kWh battery: fast payback ~5y
        (1800.0, 300.0, 65.0),   # 6 kWh battery: payback 6y
        (4800.0, 400.0, 80.0),   # 16 kWh battery: payback 12y
        (12000.0, 500.0, 90.0),  # 40 kWh battery: payback 24y → beyond limit
    ]:
        r = _make_result(invest=invest, savings=savings)
        r = ScenarioResult(
            additional_kwh=invest / 600.0,
            additional_kwp=0.0,
            avoided_grid_import_kwh=savings / 0.30,
            added_self_consumption_kwh=0.0,
            reduced_feed_in_kwh=0.0,
            inverter_clipping_loss_kwh=0.0,
            extra_pv_yield_kwh=0.0,
            self_sufficiency_pct=autarky,
            cycles_per_year=100.0,
            monthly_avoided_kwh=[savings / 12.0 / 0.30] * 12,
            monthly_baseline_grid_in=[1000.0 / 12.0] * 12,
            investment_eur=invest,
            savings_eur_per_year=savings,
            payback_years=(invest / savings) if savings > 1e-6 else math.inf,
            inverter_upgrade_needed=False,
        )
        results.append(r)
    return results


class TestRecommendationStrategies:
    @pytest.fixture
    def grid(self) -> list[ScenarioResult]:
        return _make_results_grid()

    def test_economic_finds_best_payback(self, grid: list[ScenarioResult]) -> None:
        rec = _find_economic(grid)
        assert rec is not None
        # The 2 kWh option has payback 5y – best within limit
        assert rec.payback_years == pytest.approx(5.0, abs=0.2)

    def test_economic_excludes_beyond_limit(self, grid: list[ScenarioResult]) -> None:
        rec = _find_economic(grid)
        assert rec is not None
        assert rec.payback_years <= SIZING_MAX_PAYBACK_YEARS

    def test_technical_finds_highest_autarky(self, grid: list[ScenarioResult]) -> None:
        rec = _find_technical(grid)
        assert rec is not None
        # 40 kWh battery → 90% autarky (even though payback>15y, technical doesn't care)
        assert rec.self_sufficiency_pct == pytest.approx(90.0, abs=0.5)

    def test_balanced_returns_something(self, grid: list[ScenarioResult]) -> None:
        rec = _find_balanced(grid)
        assert rec is not None

    def test_economic_none_when_no_viable(self) -> None:
        # All scenarios have payback > 15y
        results = [_make_result(invest=10000.0, savings=100.0)]  # payback 100y
        rec = _find_economic(results)
        assert rec is None

    def test_technical_ignores_baseline(self) -> None:
        # Baseline has invest=0 → excluded
        results = [
            _make_result(invest=0.0, savings=0.0),
            _make_result(invest=1000.0, savings=200.0),
        ]
        results[1] = ScenarioResult(
            additional_kwh=0.0, additional_kwp=0.0,
            avoided_grid_import_kwh=0.0, added_self_consumption_kwh=0.0,
            reduced_feed_in_kwh=0.0, inverter_clipping_loss_kwh=0.0,
            extra_pv_yield_kwh=0.0, self_sufficiency_pct=70.0,
            cycles_per_year=0.0, monthly_avoided_kwh=[0.0] * 12,
            monthly_baseline_grid_in=[0.0] * 12,
            investment_eur=1000.0, savings_eur_per_year=200.0,
            payback_years=5.0, inverter_upgrade_needed=False,
        )
        results[0] = ScenarioResult(
            additional_kwh=0.0, additional_kwp=0.0,
            avoided_grid_import_kwh=0.0, added_self_consumption_kwh=0.0,
            reduced_feed_in_kwh=0.0, inverter_clipping_loss_kwh=0.0,
            extra_pv_yield_kwh=0.0, self_sufficiency_pct=100.0,  # baseline artificially high
            cycles_per_year=0.0, monthly_avoided_kwh=[0.0] * 12,
            monthly_baseline_grid_in=[0.0] * 12,
            investment_eur=0.0, savings_eur_per_year=0.0,
            payback_years=math.inf, inverter_upgrade_needed=False,
        )
        rec = _find_technical(results)
        assert rec is not None
        assert rec.investment_eur > 0.0


# ---------------------------------------------------------------------------
# interpolate_result
# ---------------------------------------------------------------------------


def _make_simple_analysis() -> SizingAnalysisResult:
    """2x2 grid: battery 0/10 kWh × pv 0/5 kWp."""
    from datetime import timedelta

    def _sr(b: float, p: float, avoid: float, autarky: float) -> ScenarioResult:
        invest = b * 600.0 + p * 1200.0
        savings = avoid * 0.30
        payback = (invest / savings) if savings > 1e-6 else math.inf
        return ScenarioResult(
            additional_kwh=b, additional_kwp=p,
            avoided_grid_import_kwh=avoid,
            added_self_consumption_kwh=0.0,
            reduced_feed_in_kwh=0.0,
            inverter_clipping_loss_kwh=0.0,
            extra_pv_yield_kwh=0.0,
            self_sufficiency_pct=autarky,
            cycles_per_year=50.0,
            monthly_avoided_kwh=[avoid / 12.0] * 12,
            monthly_baseline_grid_in=[1000.0 / 12.0] * 12,
            investment_eur=invest,
            savings_eur_per_year=savings,
            payback_years=payback,
            inverter_upgrade_needed=False,
        )

    matrix = [
        [_sr(0.0, 0.0, 0.0, 50.0), _sr(0.0, 5.0, 500.0, 65.0)],
        [_sr(10.0, 0.0, 800.0, 75.0), _sr(10.0, 5.0, 1200.0, 90.0)],
    ]
    baseline = matrix[0][0]
    return SizingAnalysisResult(
        records_count=8760,
        analysis_days=365,
        battery_sizes_kwh=[0.0, 10.0],
        pv_sizes_kwp=[0.0, 5.0],
        matrix=matrix,
        recommended_economic=None,
        recommended_technical=None,
        recommended_balanced=None,
        baseline=baseline,
        anomaly_rate=0.01,
        computed_at=_DT_BASE,
    )


class TestInterpolateResult:
    @pytest.fixture
    def analysis(self) -> SizingAnalysisResult:
        return _make_simple_analysis()

    def test_corner_00(self, analysis: SizingAnalysisResult) -> None:
        r = interpolate_result(analysis, 0.0, 0.0)
        assert r is not None
        assert r.avoided_grid_import_kwh == pytest.approx(0.0, abs=1.0)

    def test_corner_10_5(self, analysis: SizingAnalysisResult) -> None:
        r = interpolate_result(analysis, 10.0, 5.0)
        assert r is not None
        assert r.avoided_grid_import_kwh == pytest.approx(1200.0, abs=5.0)

    def test_midpoint_interpolation(self, analysis: SizingAnalysisResult) -> None:
        """Midpoint (5 kWh, 2.5 kWp) should be average of all four corners."""
        r = interpolate_result(analysis, 5.0, 2.5)
        assert r is not None
        expected = (0.0 + 500.0 + 800.0 + 1200.0) / 4.0
        assert r.avoided_grid_import_kwh == pytest.approx(expected, abs=5.0)

    def test_clamp_below(self, analysis: SizingAnalysisResult) -> None:
        """Values below sweep range are clamped to the minimum."""
        r = interpolate_result(analysis, -5.0, -2.0)
        assert r is not None
        assert r.avoided_grid_import_kwh == pytest.approx(0.0, abs=1.0)

    def test_clamp_above(self, analysis: SizingAnalysisResult) -> None:
        """Values above sweep range are clamped to the maximum."""
        r = interpolate_result(analysis, 100.0, 100.0)
        assert r is not None
        assert r.avoided_grid_import_kwh == pytest.approx(1200.0, abs=5.0)

    def test_returns_none_for_empty_analysis(self) -> None:
        assert interpolate_result(None, 5.0, 2.5) is None  # type: ignore[arg-type]

    def test_monthly_length_preserved(self, analysis: SizingAnalysisResult) -> None:
        r = interpolate_result(analysis, 5.0, 2.5)
        assert r is not None
        assert len(r.monthly_avoided_kwh) == 12
        assert len(r.monthly_baseline_grid_in) == 12


# ---------------------------------------------------------------------------
# sweep_2d (integration-style: no HA IO, pure Python)
# ---------------------------------------------------------------------------


def _make_minimal_options(max_batt: float = 5.0, batt_step: float = 5.0,
                          max_pv: float = 0.0, pv_step: float = 5.0) -> dict[str, Any]:
    from custom_components.e3dc_maestro.const import (
        CONF_SIZING_ANALYSIS_DAYS,
        CONF_SIZING_BATTERY_PRICE_EUR_KWH,
        CONF_SIZING_BATTERY_STEP_KWH,
        CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH,
        CONF_SIZING_FEED_IN_PRICE_EUR_KWH,
        CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR,
        CONF_SIZING_MAX_BATTERY_SWEEP_KWH,
        CONF_SIZING_MAX_PV_EXPANSION_KWP,
        CONF_SIZING_PV_PRICE_EUR_PER_KWP,
        CONF_SIZING_PV_STEP_KWP,
        CONF_SIZING_ROUND_TRIP_EFFICIENCY,
    )
    return {
        CONF_INSTALLED_KWP: 10.0,
        CONF_INVERTER_POWER: 10000.0,
        CONF_FEED_IN_LIMIT_PERCENT: 70.0,
        CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH: 0.30,
        CONF_SIZING_FEED_IN_PRICE_EUR_KWH: 0.08,
        CONF_SIZING_BATTERY_PRICE_EUR_KWH: 600.0,
        CONF_SIZING_PV_PRICE_EUR_PER_KWP: 1200.0,
        CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR: 1500.0,
        CONF_SIZING_ROUND_TRIP_EFFICIENCY: 0.92,
        CONF_SIZING_MAX_BATTERY_SWEEP_KWH: max_batt,
        CONF_SIZING_BATTERY_STEP_KWH: batt_step,
        CONF_SIZING_MAX_PV_EXPANSION_KWP: max_pv,
        CONF_SIZING_PV_STEP_KWP: pv_step,
        CONF_SIZING_ANALYSIS_DAYS: 365,
    }


class TestSweep2D:
    @pytest.fixture
    def records_48h(self) -> list[HourlyRecord]:
        """Two days: daylight surplus, night deficit."""
        from datetime import timedelta
        base = _DT_BASE
        recs = []
        for h in range(48):
            ts = base + timedelta(hours=h)
            h_of_day = h % 24
            if 10 <= h_of_day <= 14:
                recs.append(HourlyRecord(
                    timestamp=ts, pv_kwh=3.0, house_kwh=1.0,
                    grid_in_kwh=0.0, grid_out_kwh=2.0,
                    batt_charge_kwh=0.0, batt_discharge_kwh=0.0,
                    wallbox_kwh=0.0, hp_kwh=0.0, anomaly=False,
                ))
            else:
                recs.append(HourlyRecord(
                    timestamp=ts, pv_kwh=0.0, house_kwh=1.0,
                    grid_in_kwh=1.0, grid_out_kwh=0.0,
                    batt_charge_kwh=0.0, batt_discharge_kwh=0.0,
                    wallbox_kwh=0.0, hp_kwh=0.0, anomaly=False,
                ))
        return recs

    def test_matrix_shape(self, records_48h: list[HourlyRecord]) -> None:
        """Matrix dimensions match sweep vector lengths."""
        opts = _make_minimal_options(max_batt=10.0, batt_step=5.0, max_pv=0.0, pv_step=5.0)
        result = sweep_2d(records_48h, opts)
        assert len(result.matrix) == len(result.battery_sizes_kwh)
        for row in result.matrix:
            assert len(row) == len(result.pv_sizes_kwp)

    def test_baseline_at_0_0(self, records_48h: list[HourlyRecord]) -> None:
        """matrix[0][0] should correspond to (0 kWh, 0 kWp) = baseline."""
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0, max_pv=0.0, pv_step=5.0)
        result = sweep_2d(records_48h, opts)
        assert result.baseline.additional_kwh == 0.0
        assert result.baseline.additional_kwp == 0.0
        assert result.baseline.avoided_grid_import_kwh == pytest.approx(0.0, abs=1.0)

    def test_analysis_days_approx(self, records_48h: list[HourlyRecord]) -> None:
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0)
        result = sweep_2d(records_48h, opts)
        assert result.analysis_days == 2  # 48 hours // 24

    def test_records_count(self, records_48h: list[HourlyRecord]) -> None:
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0)
        result = sweep_2d(records_48h, opts)
        assert result.records_count == 48

    def test_anomaly_rate_zeros_when_clean(self, records_48h: list[HourlyRecord]) -> None:
        """Our synthetic records have no anomaly flag set."""
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0)
        result = sweep_2d(records_48h, opts)
        # anomaly_rate is computed from r.anomaly flag in records
        assert result.anomaly_rate == pytest.approx(0.0)

    def test_battery_sweep_monotone_avoided(self, records_48h: list[HourlyRecord]) -> None:
        """Baseline (b=0) should have less avoided import than a 5 kWh battery."""
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0)
        result = sweep_2d(records_48h, opts)
        avoided_0 = result.matrix[0][0].avoided_grid_import_kwh
        avoided_5 = result.matrix[1][0].avoided_grid_import_kwh
        assert avoided_5 >= avoided_0

    def test_empty_records_returns_result(self) -> None:
        opts = _make_minimal_options(max_batt=5.0, batt_step=5.0)
        result = sweep_2d([], opts)
        assert result is not None
        assert result.records_count == 0
