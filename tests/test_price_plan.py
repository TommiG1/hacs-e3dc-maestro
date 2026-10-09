"""Szenario-Tests für den Preisplaner (control_price_plan)."""
from __future__ import annotations

import pytest

from custom_components.e3dc_maestro.control_price_plan import plan_price_charging


def _plan(prices, cons, pv=None, **overrides):
    n = len(prices)
    kwargs = dict(
        slot_hours=[1.0] * n,
        prices=prices,
        consumption_kwh=cons if isinstance(cons, list) else [cons] * n,
        pv_kwh=pv if pv is not None else [0.0] * n,
        soc_pct=20.0,
        capacity_kwh=10.0,
        floor_pct=5.0,
        ceiling_pct=90.0,
        max_charge_kw=5.0,
        budget_kwh=20.0,
    )
    kwargs.update(overrides)
    return plan_price_charging(**kwargs)


def _day_30_60():
    """24 h: Nacht 30 ct, Tag 40 ct, Abendspitze 60 ct."""
    prices = [0.40] * 24
    for i in range(0, 6):
        prices[i] = 0.30
    for i in range(18, 22):
        prices[i] = 0.60
    return prices


class TestPricePlanBasics:
    def test_charges_cheap_window_to_avoid_expensive_import(self):
        """Kernfall: 30 ct jetzt, später 60 ct → im günstigen Fenster laden."""
        plan = _plan(_day_30_60(), 0.5)
        assert plan.total_grid_charge_kwh > 0
        # Geladen wird nur im 30-ct-Fenster (Slots 0–5), nie in der Spitze.
        assert all(g == 0 for i, g in enumerate(plan.grid_charge_kwh) if i >= 6)
        assert plan.expected_saving_eur > 0
        # In den 60-ct-Slots (18–21) darf kein Netzbezug mehr übrig sein.
        assert sum(plan.planned_import_kwh[18:22]) == pytest.approx(0.0, abs=1e-6)
        assert sum(plan.baseline_import_kwh[18:22]) > 0

    def test_flat_price_no_charge(self):
        plan = _plan([0.30] * 24, 0.5)
        assert plan.total_grid_charge_kwh == 0
        assert plan.charge_now is False
        assert plan.target_soc_pct is None
        assert "keine Netzladung" in plan.reason

    def test_spread_too_small_no_charge(self):
        """30 ct → 34 ct: nach Wirkungsgrad (0,85) keine lohnende Spanne."""
        prices = [0.30] * 6 + [0.34] * 18
        plan = _plan(prices, 0.5)
        assert plan.total_grid_charge_kwh == 0

    def test_pv_rich_day_no_charge(self):
        """PV deckt den Bedarf → kein Defizit, kein Netzladen trotz Preisspanne."""
        plan = _plan(_day_30_60(), 0.5, pv=[1.0] * 24)
        assert plan.total_grid_charge_kwh == 0

    def test_two_peaks_two_charge_windows(self):
        """Issue #14: zwei Preisspitzen → zwei getrennte günstige Ladefenster."""
        prices = [0.40] * 24
        for i in (2, 3, 12, 13):
            prices[i] = 0.20
        for i in (6, 7, 18, 19):
            prices[i] = 0.60
        cons = [0.0] * 24
        for i in (6, 7, 18, 19):
            cons[i] = 2.0
        plan = _plan(
            prices, cons, soc_pct=0.0, capacity_kwh=4.0,
            floor_pct=0.0, ceiling_pct=100.0, max_charge_kw=5.0,
        )
        charged = {i for i, g in enumerate(plan.grid_charge_kwh) if g > 0}
        assert charged & {2, 3}
        assert charged & {12, 13}
        assert charged <= {2, 3, 12, 13}

    def test_negative_price_charges(self):
        prices = [-0.05, -0.05] + [0.30] * 22
        plan = _plan(prices, 0.3)
        assert plan.grid_charge_kwh[0] + plan.grid_charge_kwh[1] > 0
        assert all(g == 0 for g in plan.grid_charge_kwh[2:])


class TestPricePlanSafety:
    def test_floor_is_unusable_capacity(self):
        """Hoher Boden (Notstromreserve): nur der Bereich darüber zählt."""
        low_floor = _plan(_day_30_60(), 0.5, floor_pct=5.0, soc_pct=5.0)
        high_floor = _plan(_day_30_60(), 0.5, floor_pct=80.0, soc_pct=5.0,
                           ceiling_pct=90.0)
        assert low_floor.total_grid_charge_kwh > 0
        # Bei 80 % Boden und 90 % Deckel ist nur 1 kWh nutzbar; um dorthin zu
        # kommen, müssten ~8,8 kWh geladen werden → lohnt sich nicht.
        assert high_floor.total_grid_charge_kwh < low_floor.total_grid_charge_kwh

    def test_ceiling_respected(self):
        plan = _plan(_day_30_60(), 0.5, ceiling_pct=60.0)
        assert max(plan.soc_pct) <= 60.0 + 1e-6

    def test_budget_cap(self):
        plan = _plan(_day_30_60(), 0.5, budget_kwh=1.0)
        assert plan.total_grid_charge_kwh <= 1.0 + 1e-9

    def test_zero_budget_no_charge(self):
        plan = _plan(_day_30_60(), 0.5, budget_kwh=0.0)
        assert plan.total_grid_charge_kwh == 0

    def test_charge_power_limit_per_slot(self):
        plan = _plan(_day_30_60(), 0.5, max_charge_kw=1.0)
        assert all(g <= 1.0 + 1e-9 for g in plan.grid_charge_kwh)

    def test_consumption_safety_factor_increases_charge(self):
        base = _plan(_day_30_60(), 0.3, consumption_safety_factor=1.0)
        safe = _plan(_day_30_60(), 0.3, consumption_safety_factor=1.5)
        assert safe.total_grid_charge_kwh >= base.total_grid_charge_kwh

    def test_pessimistic_pv_increases_charge(self):
        pv = [0.0] * 8 + [1.0] * 8 + [0.0] * 8
        optimistic = _plan(_day_30_60(), 0.6, pv=pv, pv_factor=1.0)
        pessimistic = _plan(_day_30_60(), 0.6, pv=pv, pv_factor=0.2)
        assert pessimistic.total_grid_charge_kwh >= optimistic.total_grid_charge_kwh

    def test_lower_efficiency_reduces_charge(self):
        good = _plan(_day_30_60(), 0.5, efficiency=0.95)
        bad = _plan(_day_30_60(), 0.5, efficiency=0.55)
        assert bad.expected_saving_eur < good.expected_saving_eur

    def test_wear_cost_can_prevent_charging(self):
        plan = _plan(_day_30_60(), 0.5, wear_eur_per_kwh=0.50)
        assert plan.total_grid_charge_kwh == 0


class TestPricePlanNow:
    def test_charge_now_and_target(self):
        """Nur der aktuelle Slot ist günstig → jetzt laden, Ziel-SoC > SoC."""
        prices = [0.20, 0.50, 0.50, 0.50]
        plan = _plan(prices, [0.0, 2.0, 2.0, 0.0], soc_pct=10.0, floor_pct=5.0)
        assert plan.charge_now is True
        assert plan.target_soc_pct is not None
        assert 10.0 < plan.target_soc_pct <= 90.0

    def test_charges_only_in_cheap_slots(self):
        """Nur die beiden günstigen Slots kommen für Netzladung in Frage."""
        prices = [0.20, 0.20, 0.50, 0.50]
        plan = _plan(prices, [0.0, 0.0, 1.0, 0.0], soc_pct=5.0, floor_pct=5.0)
        assert plan.total_grid_charge_kwh > 0
        assert plan.grid_charge_kwh[2] == 0 and plan.grid_charge_kwh[3] == 0
        assert sum(plan.planned_import_kwh) == pytest.approx(0.0, abs=1e-6)


class TestPricePlanHold:
    def test_holds_existing_energy_for_expensive_window(self):
        """Akku schon voll genug: keine Netzladung, aber Entladung bis zur
        60-ct-Spitze sperren (sonst verpufft die Energie bei 40 ct)."""
        plan = _plan(_day_30_60(), 0.5, soc_pct=30.0, floor_pct=5.0)
        assert plan.total_grid_charge_kwh == 0
        assert any(plan.hold_discharge[6:18])
        # In der Spitze wird freigegeben und der Akku deckt das Haus.
        assert all(plan.release[18:22])
        assert sum(plan.planned_import_kwh[18:22]) == pytest.approx(0.0, abs=1e-6)
        assert plan.expected_saving_eur > 0

    def test_hold_now_flag(self):
        plan = _plan(_day_30_60(), 0.5, soc_pct=30.0, floor_pct=5.0)
        assert plan.hold_now == plan.hold_discharge[0]

    def test_no_hold_on_flat_prices(self):
        plan = _plan([0.30] * 24, 0.5, soc_pct=30.0)
        assert not any(plan.hold_discharge)
        assert all(plan.release)

    def test_grid_charge_in_night_hold_through_day(self):
        """Dein Szenario: nachts 30 ct laden, tagsüber (40 ct) halten, abends (60 ct) nutzen."""
        plan = _plan(_day_30_60(), 0.5, soc_pct=5.0, floor_pct=5.0)
        assert plan.total_grid_charge_kwh > 0
        charged = [i for i, g in enumerate(plan.grid_charge_kwh) if g > 0]
        assert all(i < 6 for i in charged)
        assert any(plan.hold_discharge[6:18])
        assert sum(plan.planned_import_kwh[18:22]) == pytest.approx(0.0, abs=1e-6)

    def test_empty_or_mismatched_inputs(self):
        empty = plan_price_charging(
            slot_hours=[], prices=[], consumption_kwh=[], pv_kwh=[],
            soc_pct=20, capacity_kwh=10, floor_pct=5, ceiling_pct=90,
            max_charge_kw=5, budget_kwh=5,
        )
        assert empty.total_grid_charge_kwh == 0 and empty.charge_now is False
        mismatch = plan_price_charging(
            slot_hours=[1.0, 1.0], prices=[0.3], consumption_kwh=[1.0, 1.0],
            pv_kwh=[0.0, 0.0], soc_pct=20, capacity_kwh=10, floor_pct=5,
            ceiling_pct=90, max_charge_kw=5, budget_kwh=5,
        )
        assert mismatch.total_grid_charge_kwh == 0

    def test_quarter_hour_slots(self):
        """15-Minuten-Slots (96/Tag) funktionieren wie Stundenslots."""
        prices = []
        for h in range(24):
            prices += [0.30 if h < 6 else (0.60 if 18 <= h < 22 else 0.40)] * 4
        n = len(prices)
        plan = plan_price_charging(
            slot_hours=[0.25] * n, prices=prices,
            consumption_kwh=[0.125] * n, pv_kwh=[0.0] * n,
            soc_pct=20.0, capacity_kwh=10.0, floor_pct=5.0, ceiling_pct=90.0,
            max_charge_kw=5.0, budget_kwh=20.0,
        )
        assert plan.total_grid_charge_kwh > 0
        assert sum(plan.planned_import_kwh[72:88]) == pytest.approx(0.0, abs=1e-6)
