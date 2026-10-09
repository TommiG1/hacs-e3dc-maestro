"""Glue between live data (price curve, profiles, params) and the price planner.

Pure Python (no Home Assistant imports) so it can be unit-tested.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Sequence

from .control_price_plan import PricePlan, plan_price_charging
from .price_curve import PriceHorizon

# Konservativer PV-Abschlag auf Prognosen (Wolken, Prognosefehler).
PV_SAFETY_FACTOR = 0.8
# Ohne Prognose für morgen wird das historische Mittel nochmals abgeschwächt.
PV_HISTORIC_FACTOR = 0.7

STATUS_OK = "ok"
STATUS_NO_PRICES = "no_prices"
STATUS_NO_PROFILE = "no_profile"
STATUS_NO_ROOM = "no_room"


@dataclass
class PricePlanSnapshot:
    status: str
    message: str
    computed_at: _dt.datetime | None = None
    plan: PricePlan | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    known_until: _dt.datetime | None = None
    budget_kwh: float = 0.0
    floor_pct: float = 0.0

    @property
    def summary(self) -> str:
        """Short state text for the sensor."""
        if self.status != STATUS_OK or self.plan is None:
            return {
                STATUS_NO_PRICES: "keine Preise",
                STATUS_NO_PROFILE: "keine Verbrauchsdaten",
                STATUS_NO_ROOM: "kein Spielraum",
            }.get(self.status, "unbekannt")
        plan = self.plan
        if plan.charge_now:
            return "Netzladung jetzt"
        first_charge = next((r for r in self.rows if r["grid_charge_kwh"] > 0), None)
        if first_charge is not None:
            return f"Netzladung ab {first_charge['start_local']}"
        if plan.hold_now:
            return "Entladung halten"
        first_hold = next((r for r in self.rows if r["hold"]), None)
        if first_hold is not None:
            return f"Halten ab {first_hold['start_local']}"
        return "kein Handlungsbedarf"


def profile_w_at(profile_w: Sequence[float] | None, when: _dt.datetime) -> float:
    """Mean power (W) at ``when`` from a profile in UTC buckets (24 / 48 / 96 values)."""
    if not profile_w:
        return 0.0
    utc = when.astimezone(_dt.timezone.utc)
    minutes = utc.hour * 60 + utc.minute
    idx = int(minutes / (1440.0 / len(profile_w)))
    return float(profile_w[min(idx, len(profile_w) - 1)])


def _slot_kwh(profile_w: Sequence[float] | None, start: _dt.datetime, hours: float) -> float:
    mid = start + _dt.timedelta(hours=hours / 2.0)
    return max(0.0, profile_w_at(profile_w, mid)) / 1000.0 * hours


def compute_price_plan(
    *,
    horizon: PriceHorizon | None,
    now: _dt.datetime,
    soc_pct: float,
    capacity_kwh: float,
    floor_pct: float,
    ceiling_pct: float,
    max_charge_kw: float,
    max_discharge_kw: float | None,
    budget_per_day_kwh: float,
    grid_charged_today_kwh: float,
    efficiency: float,
    min_spread: float,
    safety_factor: float,
    wear_eur_per_kwh: float,
    feed_in_price: float,
    cons_profile_w: Sequence[float] | None,
    house_power_w: float,
    pv_today_w: Sequence[float] | None,
    pv_tomorrow_w: Sequence[float] | None,
    pv_hist_w: Sequence[float] | None,
) -> PricePlanSnapshot:
    if horizon is None or not horizon.prices:
        return PricePlanSnapshot(STATUS_NO_PRICES, "Keine gültige Preiskurve ab jetzt", now)
    if ceiling_pct <= floor_pct + 1.0 or capacity_kwh <= 0:
        return PricePlanSnapshot(
            STATUS_NO_ROOM,
            f"Kein Spielraum zwischen Boden ({floor_pct:.0f} %) und Obergrenze ({ceiling_pct:.0f} %)",
            now,
        )
    cons_ok = cons_profile_w is not None and any(v > 0 for v in cons_profile_w)
    if not cons_ok and house_power_w <= 0:
        return PricePlanSnapshot(STATUS_NO_PROFILE, "Noch keine Verbrauchsstatistik", now)

    local_today = now.date()
    consumption: list[float] = []
    pv: list[float] = []
    starts: list[_dt.datetime] = []
    cursor = now
    for hours in horizon.slot_hours:
        starts.append(cursor)
        if cons_ok:
            consumption.append(_slot_kwh(cons_profile_w, cursor, hours))
        else:
            consumption.append(max(0.0, house_power_w) / 1000.0 * hours)
        day_offset = (cursor + _dt.timedelta(hours=hours / 2.0)).date() - local_today
        if day_offset.days <= 0:
            profile, factor = (pv_today_w, 1.0) if pv_today_w else (pv_hist_w, PV_HISTORIC_FACTOR)
        else:
            profile, factor = (
                (pv_tomorrow_w, 1.0) if pv_tomorrow_w else (pv_hist_w, PV_HISTORIC_FACTOR)
            )
        pv.append(_slot_kwh(profile, cursor, hours) * factor)
        cursor = cursor + _dt.timedelta(hours=hours)

    crosses_midnight = any(st.date() > local_today for st in starts)
    budget = max(0.0, budget_per_day_kwh - grid_charged_today_kwh)
    if crosses_midnight:
        budget += budget_per_day_kwh

    plan = plan_price_charging(
        slot_hours=horizon.slot_hours,
        prices=horizon.prices,
        consumption_kwh=consumption,
        pv_kwh=pv,
        soc_pct=soc_pct,
        capacity_kwh=capacity_kwh,
        floor_pct=floor_pct,
        ceiling_pct=ceiling_pct,
        max_charge_kw=max_charge_kw,
        budget_kwh=budget,
        max_discharge_kw=max_discharge_kw,
        efficiency=efficiency,
        min_spread=min_spread,
        wear_eur_per_kwh=wear_eur_per_kwh,
        feed_in_price=feed_in_price,
        consumption_safety_factor=safety_factor,
        pv_factor=PV_SAFETY_FACTOR,
    )

    rows = []
    for i, start in enumerate(starts):
        rows.append({
            "start": start.isoformat(),
            "start_local": start.strftime("%H:%M"),
            "hours": round(horizon.slot_hours[i], 3),
            "price": round(horizon.prices[i], 4),
            "grid_charge_kwh": round(plan.grid_charge_kwh[i], 3),
            "hold": bool(plan.hold_discharge[i]),
            "release": bool(plan.release[i]),
            "soc_pct": round(plan.soc_pct[i], 1),
            "import_kwh": round(plan.planned_import_kwh[i], 3),
            "baseline_import_kwh": round(plan.baseline_import_kwh[i], 3),
            "consumption_kwh": round(consumption[i], 3),
            "pv_kwh": round(pv[i], 3),
        })
    return PricePlanSnapshot(
        status=STATUS_OK,
        message=plan.reason,
        computed_at=now,
        plan=plan,
        rows=rows,
        known_until=horizon.known_until,
        budget_kwh=round(budget, 2),
        floor_pct=floor_pct,
    )
