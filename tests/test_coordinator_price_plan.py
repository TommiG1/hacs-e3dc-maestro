"""Smoke-Test des Preisplan-Mixins (Schattenmodus) mit Fake-Coordinator."""
from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

from custom_components.e3dc_maestro.control_engine import MaestroParams, MaestroState
from custom_components.e3dc_maestro.coordinator_price_plan import CoordinatorPricePlanMixin

TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 10, 9, 18, 5, tzinfo=TZ)


def _raw(day, prices):
    base = dt.datetime(2026, 10, day, tzinfo=TZ)
    return [
        {"start": (base + dt.timedelta(hours=i)).isoformat(),
         "end": (base + dt.timedelta(hours=i + 1)).isoformat(), "value": p}
        for i, p in enumerate(prices)
    ]


class _Fake(CoordinatorPricePlanMixin):
    def __init__(self, enabled=True, attrs=None):
        self._params = MaestroParams()
        self._params.price_plan_enabled = enabled
        self.entry = SimpleNamespace(options={"price_sensor": "sensor.preis"})
        state = None
        if attrs is not None:
            state = SimpleNamespace(state="0.3", attributes=attrs)
        self.hass = SimpleNamespace(
            states=SimpleNamespace(get=lambda _eid: state),
            async_add_executor_job=self._run,
        )
        self.stats = {}
        self._consumption_stats = SimpleNamespace(hourly_profile_w=[500.0] * 24)
        self._pv_stats = None

    async def _run(self, fn):
        return fn()

    def _read_pv_forecast_profile(self, now, days_ahead=0, ignore_enabled=False):
        return None


def _state():
    return MaestroState(
        soc=15.0, pv_power=0.0, grid_power=0.0, battery_power=0.0, house_power=500.0
    )


def test_disabled_does_nothing():
    c = _Fake(enabled=False, attrs={})
    asyncio.run(c._async_update_price_plan(_state(), NOW))
    assert c.price_plan is None


def test_no_price_sensor_data_gives_status():
    c = _Fake(attrs={})
    asyncio.run(c._async_update_price_plan(_state(), NOW))
    assert c.price_plan is not None
    assert c.price_plan.status == "no_prices"
    assert c.price_plan.summary == "keine Preise"


def test_plan_computed_and_cached():
    prices_today = [0.30] * 24
    prices_tomorrow = [0.19] * 6 + [0.30] * 12 + [0.60] * 4 + [0.30] * 2
    attrs = {"raw_today": _raw(9, prices_today), "raw_tomorrow": _raw(10, prices_tomorrow)}
    c = _Fake(attrs=attrs)
    c._params.max_grid_charge_kwh = 8.0
    asyncio.run(c._async_update_price_plan(_state(), NOW))
    snap = c.price_plan
    assert snap.status == "ok"
    assert snap.plan.total_grid_charge_kwh > 0
    assert all(r["price"] <= 0.30 for r in snap.rows if r["grid_charge_kwh"] > 0)
    # Zweiter Aufruf im selben 5-Minuten-Fenster liefert dasselbe Objekt (Cache).
    asyncio.run(c._async_update_price_plan(_state(), NOW + dt.timedelta(minutes=1)))
    assert c.price_plan is snap


def test_disabling_clears_plan():
    c = _Fake(attrs={"raw_today": _raw(9, [0.3] * 24)})
    asyncio.run(c._async_update_price_plan(_state(), NOW))
    assert c.price_plan is not None
    c._params.price_plan_enabled = False
    asyncio.run(c._async_update_price_plan(_state(), NOW))
    assert c.price_plan is None


class TestPricePlanAction:
    """Der Koordinator reicht den Plan nur frisch und nur bei eingeschalteter Steuerung weiter."""

    def _fake_with_plan(self, active=True, age_s=60, status="ok"):
        from custom_components.e3dc_maestro.control_price_plan import PricePlan
        from custom_components.e3dc_maestro.price_plan_runner import PricePlanSnapshot

        f = _Fake()
        f._params.price_plan_active = active
        f.price_plan = PricePlanSnapshot(
            status=status, message="m", computed_at=NOW - dt.timedelta(seconds=age_s),
            plan=PricePlan(charge_now=True, hold_now=False, target_soc_pct=80.0, reason="r"),
        )
        return f

    def test_returns_action_when_active_and_fresh(self):
        a = self._fake_with_plan()._price_plan_action(NOW)
        assert a is not None and a.charge_now and a.target_soc == 80.0

    def test_none_when_switch_off(self):
        assert self._fake_with_plan(active=False)._price_plan_action(NOW) is None

    def test_none_when_stale(self):
        assert self._fake_with_plan(age_s=25 * 60)._price_plan_action(NOW) is None

    def test_none_when_status_not_ok(self):
        assert self._fake_with_plan(status="no_prices")._price_plan_action(NOW) is None

    def test_none_without_plan(self):
        f = _Fake()
        f._params.price_plan_active = True
        assert f._price_plan_action(NOW) is None
