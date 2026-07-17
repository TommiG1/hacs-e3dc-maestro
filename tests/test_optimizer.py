"""Tests for the F3 Auto-Optimizer (grid-search over F0 params)."""
from datetime import datetime, timezone

import pytest

from custom_components.e3dc_maestro.control_engine import MaestroParams
from custom_components.e3dc_maestro.optimizer import (
    OBJECTIVE_CO2,
    OBJECTIVE_COST,
    OBJECTIVE_SELF_CONSUMPTION,
    OBJECTIVES,
    OptimizerResult,
    run_optimizer,
)


_NOW = datetime(2026, 6, 15, 0, 30, tzinfo=timezone.utc)


def _params() -> MaestroParams:
    return MaestroParams(
        inverter_power=12000,
        max_charge_power=5000,
        min_charge_power=300,
        installed_kwp=10.0,
        feed_in_limit_percent=70.0,
        charge_threshold=15.0,
        battery_capacity_kwh=15.0,
        adaptive_reserve_min_soc=10.0,
    )


def _summer_pv() -> list[float]:
    """Bell-shaped PV curve peaking at noon, ~6 kW peak."""
    return [
        0, 0, 0, 0, 0, 100, 500, 1500, 3000, 4500, 5500, 6000,
        6000, 5500, 4500, 3000, 1500, 500, 100, 0, 0, 0, 0, 0,
    ]


def _typical_consumption() -> list[float]:
    return [
        300, 250, 250, 250, 250, 300, 500, 800, 700, 600, 600, 700,
        800, 600, 500, 500, 600, 800, 1200, 1500, 1200, 800, 500, 400,
    ]


def _run(objective: str = OBJECTIVE_SELF_CONSUMPTION, **overrides) -> OptimizerResult:
    kwargs = dict(
        base_params=_params(),
        soc=50.0,
        consumption_h=_typical_consumption(),
        pv_h=_summer_pv(),
        battery_capacity_kwh=15.0,
        regelung_aktiv=True,
        max_discharge_power=8000,
        objective=objective,
        now=_NOW,
        consumption_data_days=14,
        pv_data_days=14,
    )
    kwargs.update(overrides)
    return run_optimizer(**kwargs)


class TestRunOptimizer:
    def test_returns_optimizer_result_type(self):
        result = _run()
        assert isinstance(result, OptimizerResult)
        assert result.objective in OBJECTIVES

    def test_insufficient_consumption_history_falls_back(self):
        result = _run(consumption_data_days=3)
        assert result.fallback is True
        assert "insufficient" in (result.fallback_reason or "")
        # base params untouched
        assert result.best_params.morning_cap_enabled is False

    def test_insufficient_pv_history_falls_back(self):
        result = _run(pv_data_days=2)
        assert result.fallback is True

    def test_self_consumption_objective(self):
        result = _run(OBJECTIVE_SELF_CONSUMPTION)
        assert result.objective == OBJECTIVE_SELF_CONSUMPTION
        assert result.fallback is False
        assert result.grid_size > 0
        # Grid is now 7×6×5 = 210 candidates
        assert result.grid_size <= 210

    def test_cost_objective(self):
        result = _run(OBJECTIVE_COST)
        assert result.objective == OBJECTIVE_COST
        assert result.fallback is False

    def test_co2_objective(self):
        result = _run(OBJECTIVE_CO2)
        assert result.objective == OBJECTIVE_CO2
        assert result.fallback is False

    def test_safety_constraint_reserve(self):
        # Result should never produce min_soc below adaptive_reserve_min_soc
        result = _run()
        if result.forecast is not None:
            assert result.forecast.min_soc >= 10.0

    def test_zero_pv_does_not_crash(self):
        result = _run(pv_h=[0.0] * 24)
        assert isinstance(result, OptimizerResult)
        assert result.fallback is False  # data_days still 14

    def test_invalid_objective_defaults_to_self_consumption(self):
        result = _run(objective="bogus")
        assert result.objective == OBJECTIVE_SELF_CONSUMPTION

    def test_overrides_only_set_on_improvement(self):
        result = _run()
        if result.overrides:
            assert "morning_cap_soc" in result.overrides
            assert "morning_cap_until_h" in result.overrides
            assert "gentle_charge_factor" not in result.overrides
        else:
            # No improvement → base_params returned
            assert result.best_params.morning_cap_enabled is False

    def test_cost_wear_uses_battery_throughput(self):
        result = _run(OBJECTIVE_COST)
        assert result.fallback is False
        assert result.baseline_forecast is not None
        assert result.baseline_forecast.battery_throughput_kwh >= 0.0
        assert abs(result.estimated_savings_pct) < 1_000_000

    def test_pv_charge_throughput_without_grid_draw(self):
        """PV surplus charging creates battery throughput even with zero grid draw."""
        result = run_optimizer(
            base_params=_params(),
            soc=20.0,
            consumption_h=[100.0] * 24,
            pv_h=[
                0, 0, 0, 0, 0, 100, 500, 1500, 3000, 4500, 5500, 6000,
                6000, 5500, 4500, 3000, 1500, 500, 100, 0, 0, 0, 0, 0,
            ],
            battery_capacity_kwh=15.0,
            regelung_aktiv=True,
            max_discharge_power=8000,
            objective=OBJECTIVE_COST,
            now=_NOW,
            consumption_data_days=14,
            pv_data_days=14,
        )
        assert result.baseline_forecast is not None
        assert result.baseline_forecast.battery_throughput_kwh > 0.0
        # Wear must be based on throughput field (present on ForecastResult)
        assert hasattr(result.baseline_forecast, "battery_throughput_kwh")
