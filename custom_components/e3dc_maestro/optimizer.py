"""F3: Auto-Optimierer.

Grid-search over the F0 flat-curve parameters using the F1 forecast simulator
as the objective function. Runs at most once per day (after midnight) in the
coordinator, see ``_async_maybe_run_optimizer``.

The result is a ``MaestroParams`` *override* that the coordinator applies on
top of the user's manual configuration. Manual writes (entity service calls)
invalidate the override immediately so the user always wins.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .control_engine import MaestroParams
from .forecast import simulate_next_24h, ForecastResult

_LOGGER = logging.getLogger(__name__)

OBJECTIVE_SELF_CONSUMPTION = "self_consumption"
OBJECTIVE_COST = "cost"
OBJECTIVE_CO2 = "co2"
OBJECTIVES = (OBJECTIVE_SELF_CONSUMPTION, OBJECTIVE_COST, OBJECTIVE_CO2)

# Grid-search space.
# Extended cap-soc/until-h ranges capture high-PV summer days where keeping
# headroom until noon avoids midday curtailment.
_MORNING_CAP_SOC_GRID = (20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0)
_MORNING_CAP_UNTIL_H_GRID = (7.0, 8.0, 9.0, 10.0, 11.0, 12.0)

# Cost / CO2 model coefficients (typical DE values, May 2026)
# v0.2.0: buy/sell prices are now read from MaestroParams (configurable).
# These constants only act as fallback when params are unavailable.
_GRID_BUY_PRICE_FALLBACK = 0.30      # €/kWh
_GRID_SELL_PRICE_FALLBACK = 0.08     # €/kWh feed-in
_GRID_CO2_KG_PER_KWH = 0.4           # kg CO2 per kWh (DE mix avg)


def _wear_eur_per_kwh(params: MaestroParams) -> float:
    """Approximate battery wear cost per kWh of throughput.

    Throughput ~= 2 × capacity per full cycle (one charge + one discharge).
    Energy lifetime = total_cycles × 2 × capacity.
    """
    cap = max(getattr(params, "battery_capacity_kwh", 10.0), 1.0)
    cycles = max(getattr(params, "battery_total_cycles", 5000.0), 100.0)
    capex = max(getattr(params, "battery_capex_eur", 8000.0), 0.0)
    return capex / (cycles * 2.0 * cap)


@dataclass
class OptimizerResult:
    best_params: MaestroParams
    best_score: float
    objective: str
    estimated_savings_pct: float = 0.0
    estimated_savings_eur: float = 0.0
    grid_size: int = 0
    fallback: bool = False
    fallback_reason: str | None = None
    # Description of which parameters changed vs. base
    overrides: dict[str, Any] = field(default_factory=dict)
    forecast: ForecastResult | None = None
    # Baseline (no-override) 24h forecast — used to compute live deltas
    baseline_forecast: ForecastResult | None = None


def _score(result: ForecastResult, objective: str, params: MaestroParams | None = None) -> float:
    """Higher is better for all objectives (we negate cost/CO2).

    Curtailment (pv_curtailed_kwh) is penalised in every objective because
    it represents PV energy that cannot be used regardless of strategy choice.
    A higher cap-soc combined with a later cap-until-h keeps battery headroom
    for the midday peak and reduces curtailment losses.

    v0.2.0: cost/feed-in prices and wear cost are read from ``params``.
    """
    curtailed = result.pv_curtailed_kwh
    buy = getattr(params, "fixed_buy_price", _GRID_BUY_PRICE_FALLBACK) if params else _GRID_BUY_PRICE_FALLBACK
    sell = getattr(params, "feed_in_price", _GRID_SELL_PRICE_FALLBACK) if params else _GRID_SELL_PRICE_FALLBACK
    if objective == OBJECTIVE_SELF_CONSUMPTION:
        ss = result.self_sufficiency or 0.0
        # Penalise grid draw (not covered by own PV/battery) and curtailment
        # (PV that could have been stored but battery was full)
        return ss * 100.0 - result.grid_draw_kwh * 0.5 - curtailed * 1.5
    if objective == OBJECTIVE_COST:
        cost = result.grid_draw_kwh * buy - result.grid_feed_in_kwh * sell
        # Curtailed PV = lost feed-in income
        # Wear cost: based on simulated battery throughput (charge+discharge).
        throughput = getattr(result, "battery_throughput_kwh", 0.0) or 0.0
        wear = throughput * (_wear_eur_per_kwh(params) if params else 0.15)
        return -cost - curtailed * sell - wear
    if objective == OBJECTIVE_CO2:
        # Curtailed PV could have displaced grid CO2
        return -(result.grid_draw_kwh * _GRID_CO2_KG_PER_KWH) - curtailed * _GRID_CO2_KG_PER_KWH
    return 0.0


def _build_candidate(
    base: MaestroParams, cap_soc: float, until_h: float
) -> MaestroParams:
    """Return a copy of ``base`` with morning-cap params overridden.

    gentle_charge is intentionally NOT touched: it controls charge speed
    (battery health / comfort), has no relationship to tariff cost or
    self-consumption, and must remain under the user's control.
    """
    return dataclasses.replace(
        base,
        morning_cap_enabled=True,
        morning_cap_soc=cap_soc,
        morning_cap_until_h=until_h,
    )


def run_optimizer(
    *,
    base_params: MaestroParams,
    soc: float,
    consumption_h: list[float],
    pv_h: list[float],
    battery_capacity_kwh: float,
    regelung_aktiv: bool,
    max_discharge_power: float,
    objective: str,
    now: datetime,
    consumption_data_days: int = 0,
    pv_data_days: int = 0,
    min_data_days: int = 7,
    pv_h_day2: list[float] | None = None,
    consumption_h_day2: list[float] | None = None,
) -> OptimizerResult:
    """Evaluate the F0 grid and return the best ``MaestroParams`` override.

    Falls back to ``base_params`` (no override) if data quality is insufficient.

    If ``pv_h_day2`` is provided, the simulation horizon is extended to 48 h.
    This allows the optimizer to penalise strategies that leave the battery
    too low at the end of day 1 when day 2 has weak PV (avoiding morning grid
    draw on the following day).
    """
    if objective not in OBJECTIVES:
        objective = OBJECTIVE_SELF_CONSUMPTION

    # Data-quality fallback: refuse to optimise on weak history
    if consumption_data_days < min_data_days or pv_data_days < min_data_days:
        return OptimizerResult(
            best_params=base_params,
            best_score=0.0,
            objective=objective,
            fallback=True,
            fallback_reason=(
                f"insufficient_history "
                f"(consumption={consumption_data_days}d, pv={pv_data_days}d, "
                f"required={min_data_days}d)"
            ),
        )

    reserve_floor = max(
        getattr(base_params, "adaptive_reserve_min_soc", 5.0),
        5.0,
    )

    # Determine simulation horizon: 48 h when day-2 PV forecast is available,
    # else fall back to the historic 24 h horizon. The day-2 lookahead lets
    # the optimizer see whether a low end-of-day-1 SoC will cause expensive
    # grid draw on day 2 (when day 2 has poor PV).
    _have_day2 = pv_h_day2 is not None and any(v > 0 for v in (pv_h_day2 or []))
    _horizon_h = 48 if _have_day2 else 24
    _cons_day2 = consumption_h_day2 if _have_day2 else None
    _pv_day2 = pv_h_day2 if _have_day2 else None

    # Baseline: no F0 override → reference for savings %
    try:
        baseline = simulate_next_24h(
            soc=soc,
            consumption_h=consumption_h,
            pv_h=pv_h,
            params=base_params,
            now=now,
            battery_capacity_kwh=battery_capacity_kwh,
            regelung_aktiv=regelung_aktiv,
            max_discharge_power=max_discharge_power,
            pv_h_day2=_pv_day2,
            consumption_h_day2=_cons_day2,
            horizon_h=_horizon_h,
        )
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.warning("Optimizer baseline failed: %s", err)
        return OptimizerResult(
            best_params=base_params,
            best_score=0.0,
            objective=objective,
            fallback=True,
            fallback_reason=f"baseline_error: {err}",
        )

    baseline_score = _score(baseline, objective, base_params)
    best_score = baseline_score
    best_params = base_params
    best_forecast = baseline
    grid_size = 0

    for cap_soc in _MORNING_CAP_SOC_GRID:
        # Safety: skip combinations that would let SoC fall below reserve
        if cap_soc < reserve_floor:
            continue
        for until_h in _MORNING_CAP_UNTIL_H_GRID:
            grid_size += 1
            candidate = _build_candidate(base_params, cap_soc, until_h)
            try:
                fc = simulate_next_24h(
                    soc=soc,
                    consumption_h=consumption_h,
                    pv_h=pv_h,
                    params=candidate,
                    now=now,
                    battery_capacity_kwh=battery_capacity_kwh,
                    regelung_aktiv=regelung_aktiv,
                    max_discharge_power=max_discharge_power,
                    pv_h_day2=_pv_day2,
                    consumption_h_day2=_cons_day2,
                    horizon_h=_horizon_h,
                )
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.debug("Optimizer candidate failed: %s", err)
                continue
            # Safety: never violate reserve
            if fc.min_soc < reserve_floor:
                continue
            score = _score(fc, objective, candidate)
            if score > best_score:
                best_score = score
                best_params = candidate
                best_forecast = fc

    # Estimate savings vs. baseline using a positive cost/draw baseline so
    # percentage values stay interpretable (higher = better for the user).
    buy = getattr(base_params, "fixed_buy_price", _GRID_BUY_PRICE_FALLBACK)
    sell = getattr(base_params, "feed_in_price", _GRID_SELL_PRICE_FALLBACK)
    wear_per_kwh = _wear_eur_per_kwh(base_params)
    base_throughput = getattr(baseline, "battery_throughput_kwh", 0.0) or 0.0
    best_throughput = getattr(best_forecast, "battery_throughput_kwh", 0.0) or 0.0
    base_net = (
        baseline.grid_feed_in_kwh * sell
        - baseline.grid_draw_kwh * buy
        - base_throughput * wear_per_kwh
    )
    best_net = (
        best_forecast.grid_feed_in_kwh * sell
        - best_forecast.grid_draw_kwh * buy
        - best_throughput * wear_per_kwh
    )
    estimated_eur = best_net - base_net

    if objective == OBJECTIVE_COST:
        base_cost = (
            baseline.grid_draw_kwh * buy
            - baseline.grid_feed_in_kwh * sell
            + base_throughput * wear_per_kwh
        )
        estimated = (estimated_eur / abs(base_cost) * 100.0) if abs(base_cost) > 1e-9 else 0.0
    elif baseline.grid_draw_kwh > 1e-9:
        estimated = (
            (baseline.grid_draw_kwh - best_forecast.grid_draw_kwh)
            / baseline.grid_draw_kwh
            * 100.0
        )
    elif baseline_score == 0:
        estimated = 0.0
    else:
        estimated = (best_score - baseline_score) / abs(baseline_score) * 100.0

    overrides: dict[str, Any] = {}
    if best_params is not base_params:
        for fld in ("morning_cap_enabled", "morning_cap_soc", "morning_cap_until_h"):
            overrides[fld] = getattr(best_params, fld)

    return OptimizerResult(
        best_params=best_params,
        best_score=best_score,
        objective=objective,
        estimated_savings_pct=round(estimated, 2),
        estimated_savings_eur=round(estimated_eur, 3),
        grid_size=grid_size,
        fallback=False,
        overrides=overrides,
        forecast=best_forecast,
        baseline_forecast=baseline,
    )
