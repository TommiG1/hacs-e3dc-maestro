"""Tests für die Verdrahtung Preiskurve → Planer (Profile, Budget, Zusammenfassung)."""
from __future__ import annotations

import datetime as dt

from custom_components.e3dc_maestro.price_curve import read_price_horizon
from custom_components.e3dc_maestro.price_plan_runner import (
    STATUS_NO_PRICES,
    STATUS_NO_PROFILE,
    STATUS_NO_ROOM,
    STATUS_OK,
    compute_price_plan,
    profile_w_at,
)

TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 10, 9, 18, 0, tzinfo=TZ)


def _raw(day, prices):
    base = dt.datetime(2026, 10, day, tzinfo=TZ)
    return [
        {"start": (base + dt.timedelta(hours=i)).isoformat(),
         "end": (base + dt.timedelta(hours=i + 1)).isoformat(), "value": p}
        for i, p in enumerate(prices)
    ]


def _horizon(today=None, tomorrow=None):
    attrs = {"raw_today": _raw(9, today or [0.3] * 24)}
    if tomorrow is not None:
        attrs["raw_tomorrow"] = _raw(10, tomorrow)
    return read_price_horizon(attrs, NOW)


def _run(horizon, **over):
    kw = dict(
        horizon=horizon, now=NOW, soc_pct=20.0, capacity_kwh=10.0, floor_pct=10.0,
        ceiling_pct=90.0, max_charge_kw=5.0, max_discharge_kw=5.0, budget_per_day_kwh=10.0,
        grid_charged_today_kwh=0.0, efficiency=0.85, min_spread=0.08, safety_factor=1.0,
        wear_eur_per_kwh=0.0, feed_in_price=0.08, cons_profile_w=[400.0] * 24,
        house_power_w=400.0, pv_today_w=None, pv_tomorrow_w=None, pv_hist_w=None,
    )
    kw.update(over)
    return compute_price_plan(**kw)


class TestProfile:
    def test_hourly_utc_bucket(self):
        prof = [float(h) for h in range(24)]
        # 18:30 +02:00 = 16:30 UTC → Bucket 16
        assert profile_w_at(prof, dt.datetime(2026, 10, 9, 18, 30, tzinfo=TZ)) == 16.0

    def test_half_hourly_bucket(self):
        prof = [float(i) for i in range(48)]
        assert profile_w_at(prof, dt.datetime(2026, 10, 9, 18, 40, tzinfo=TZ)) == 33.0

    def test_empty(self):
        assert profile_w_at(None, NOW) == 0.0
        assert profile_w_at([], NOW) == 0.0


class TestStatus:
    def test_no_prices(self):
        snap = _run(None)
        assert snap.status == STATUS_NO_PRICES
        assert snap.summary == "keine Preise"

    def test_no_room(self):
        snap = _run(_horizon(), floor_pct=89.5)
        assert snap.status == STATUS_NO_ROOM

    def test_no_profile(self):
        snap = _run(_horizon(), cons_profile_w=None, house_power_w=0.0)
        assert snap.status == STATUS_NO_PROFILE

    def test_falls_back_to_house_power(self):
        snap = _run(_horizon(), cons_profile_w=None, house_power_w=500.0)
        assert snap.status == STATUS_OK
        assert abs(snap.rows[1]["consumption_kwh"] - 0.5) < 1e-6


class TestPlanFromCurve:
    def _curve(self):
        # heute Abend teuer, nachts günstig, morgen Abend sehr teuer
        today = [0.30] * 24
        for h in range(18, 24):
            today[h] = 0.30
        tomorrow = [0.20] * 6 + [0.30] * 12 + [0.60] * 4 + [0.30] * 2
        return _horizon(today, tomorrow)

    def test_rows_cover_horizon_and_summary(self):
        snap = _run(self._curve(), cons_profile_w=[800.0] * 24)
        assert snap.status == STATUS_OK
        assert len(snap.rows) == len(snap.plan.grid_charge_kwh)
        assert snap.summary.startswith(("Netzladung", "Halten", "Entladung", "kein"))

    def test_plans_charge_before_expensive_window(self):
        snap = _run(self._curve(), cons_profile_w=[800.0] * 24, soc_pct=12.0)
        charged = [r for r in snap.rows if r["grid_charge_kwh"] > 0]
        assert charged, snap.message
        # Geladen wird nur in den günstigen Slots, nie in den 60-ct-Slots
        assert all(r["price"] <= 0.30 for r in charged)

    def test_budget_includes_tomorrow_when_horizon_crosses_midnight(self):
        crossing = _run(self._curve(), grid_charged_today_kwh=10.0)
        assert crossing.budget_kwh == 10.0  # heute aufgebraucht, morgen frisch
        today_only = _run(_horizon(), grid_charged_today_kwh=4.0)
        assert today_only.budget_kwh == 6.0

    def test_pv_falls_back_to_hist_with_discount(self):
        hist = [1000.0] * 24
        snap = _run(self._curve(), pv_hist_w=hist)
        tomorrow_row = next(r for r in snap.rows if r["start"].startswith("2026-10-10T12"))
        assert abs(tomorrow_row["pv_kwh"] - 0.7) < 1e-6

    def test_pv_forecast_used_for_tomorrow(self):
        snap = _run(self._curve(), pv_tomorrow_w=[2000.0] * 24, pv_hist_w=[1000.0] * 24)
        tomorrow_row = next(r for r in snap.rows if r["start"].startswith("2026-10-10T12"))
        assert abs(tomorrow_row["pv_kwh"] - 2.0) < 1e-6
