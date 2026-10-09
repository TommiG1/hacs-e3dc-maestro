"""Preisbasierte Netzlade-Planung (Preisplan).

Reine Funktion ohne Home-Assistant-Abhängigkeit: Aus einer Preiskurve sowie
Verbrauchs- und PV-Prognose pro Slot wird geplant,

* in welchen (günstigen) Slots der Akku aus dem Netz geladen wird und
* in welchen Slots die Entladung gesperrt bleibt ("halten"), damit die
  geladene Energie nicht schon in mittelteuren Slots verpufft, sondern erst
  in den teuren Slots das Haus versorgt.

Modell (je Slot)
----------------
1. Geplante Netzladung ``a`` (kWh aus dem Netz) lädt mit Wirkungsgrad
   ``efficiency`` bis zum Deckel.
2. PV − Verbrauch: Überschuss lädt den Akku (bis Deckel/Ladeleistung), Rest
   wird eingespeist. Defizit: Entladung bis zum Boden, falls "freigegeben";
   sonst (gesperrt) und für den Rest wird Netzstrom bezogen.
3. Kosten = Bezug·Preis − Einspeisung·Vergütung + Netzladung·(Preis + Verschleiß).

Lösung per dynamischer Programmierung über den gespeicherten Energieinhalt
(rückwärts Wertfunktion, vorwärts Politik mit linearer Interpolation). Bei
gleichem Ergebnis gewinnt "nicht laden" und "freigeben", d. h. Laden wird so
lange wie möglich aufgeschoben und es wird nur eingegriffen, wenn es lohnt.
Der Plan wird bei jedem Aufruf neu gerechnet (selbstkorrigierend).

Der Boden (``floor_pct``) muss vom Aufrufer als ``max(Ladeschwelle,
Notstromreserve)`` übergeben werden: Unterhalb der Reserve ist die Entladung
gesperrt, diese Kapazität darf der Plan nicht als nutzbar zählen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_EPS = 1e-9
_TIE = 1e-9
_BISECTION_ITERATIONS = 10


@dataclass
class PricePlan:
    """Ergebnis der Preisplanung (alle Listen haben eine Länge von n Slots)."""

    grid_charge_kwh: list[float] = field(default_factory=list)
    release: list[bool] = field(default_factory=list)           # Entladung erlaubt
    hold_discharge: list[bool] = field(default_factory=list)    # Entladung gezielt gesperrt
    soc_pct: list[float] = field(default_factory=list)          # SoC am Slot-Ende mit Plan
    baseline_import_kwh: list[float] = field(default_factory=list)  # Netzbezug ohne Plan
    planned_import_kwh: list[float] = field(default_factory=list)   # Netzbezug mit Plan
    total_grid_charge_kwh: float = 0.0
    expected_saving_eur: float = 0.0
    charge_now: bool = False
    hold_now: bool = False
    target_soc_pct: float | None = None
    reason: str = ""


class _Model:
    """Parameter und Einzelschritt des Akku-Modells."""

    def __init__(
        self,
        *,
        slot_hours: list[float],
        prices: list[float],
        net_kwh: list[float],
        floor_kwh: float,
        ceil_kwh: float,
        top_kwh: float,
        max_charge_kw: float,
        max_discharge_kw: float,
        efficiency: float,
        feed_in_price: float,
        wear_eur_per_kwh: float,
        step_kwh: float,
    ) -> None:
        self.h = slot_hours
        self.p = prices
        self.net = net_kwh
        self.n = len(slot_hours)
        self.floor = floor_kwh
        self.ceil = ceil_kwh
        self.max_charge_kw = max_charge_kw
        self.max_discharge_kw = max_discharge_kw
        self.eta = efficiency
        self.feed = feed_in_price
        self.wear = wear_eur_per_kwh
        self.levels = max(2, int(round(top_kwh / max(0.05, step_kwh))))
        self.q = top_kwh / self.levels if top_kwh > 0 else 1.0

    def a_options(self, i: int, budget_left: float) -> list[float]:
        max_a = min(self.max_charge_kw * self.h[i], max(0.0, budget_left))
        steps = int(max_a / self.q + _EPS)
        return [m * self.q for m in range(steps + 1)]

    def flow(self, s: float, a: float, release: bool, i: int) -> tuple[float, float, float, float, bool]:
        """Ein Slot → (s_neu, Bezug, Einspeisung, reale Kosten, Sperre wirksam)."""
        h = self.h[i]
        if a > 0.0:
            s += min(a * self.eta, max(0.0, self.ceil - s))
        net = self.net[i]
        imp = 0.0
        exp = 0.0
        held = False
        if net >= 0.0:
            room = max(0.0, self.ceil - s)
            charged = min(net, room, self.max_charge_kw * h)
            s += charged
            exp = net - charged
        else:
            need = -net
            avail = max(0.0, s - self.floor)
            if release:
                dis = min(need, avail, self.max_discharge_kw * h)
            else:
                dis = 0.0
                held = avail > _EPS
            s -= dis
            imp = need - dis
        cost = imp * self.p[i] - exp * self.feed + a * (self.p[i] + self.wear)
        return s, imp, exp, cost, held

    def interp(self, values: list[float], s: float) -> float:
        x = s / self.q
        if x <= 0.0:
            return values[0]
        k = int(x)
        if k >= self.levels:
            return values[self.levels]
        frac = x - k
        return values[k] * (1.0 - frac) + values[k + 1] * frac

    def backward(self, penalty: float, budget_left: float) -> list[list[float]]:
        """Wertfunktion V[i][k] (minimale Restkosten) für alle Slots rückwärts."""
        v: list[list[float]] = [[0.0] * (self.levels + 1) for _ in range(self.n + 1)]
        for i in range(self.n - 1, -1, -1):
            nxt = v[i + 1]
            cur = v[i]
            a_opts = self.a_options(i, budget_left)
            releases = (True, False) if self.net[i] < 0.0 else (True,)
            for k in range(self.levels + 1):
                s0 = k * self.q
                best = float("inf")
                for a in a_opts:
                    if a > 0.0 and s0 + a * self.eta > self.ceil + self.q:
                        break
                    for rel in releases:
                        s1, _, _, cost, _ = self.flow(s0, a, rel, i)
                        total = cost + a * penalty + self.interp(nxt, s1)
                        if total < best:
                            best = total
                cur[k] = best
        return v

    def forward(
        self,
        v: list[list[float]],
        stored0: float,
        penalty: float,
        budget: float,
    ) -> dict:
        s = stored0
        budget_left = budget
        grid: list[float] = []
        rel_flags: list[bool] = []
        hold_flags: list[bool] = []
        imports: list[float] = []
        stored_end: list[float] = []
        cost_real = 0.0
        for i in range(self.n):
            nxt = v[i + 1]
            a_opts = self.a_options(i, budget_left)
            releases = (True, False) if self.net[i] < 0.0 else (True,)
            best_total = float("inf")
            best: tuple[float, bool, float, float, float, float, bool] | None = None
            for a in a_opts:
                if a > 0.0 and s + a * self.eta > self.ceil + self.q:
                    break
                for rel in releases:
                    s1, imp, _, cost, held = self.flow(s, a, rel, i)
                    total = cost + a * penalty + self.interp(nxt, s1)
                    # Gleichstand → zuerst gesehene Variante (a=0, freigeben) behalten.
                    if total < best_total - _TIE:
                        best_total = total
                        best = (a, rel, s1, imp, cost, total, held)
            assert best is not None
            a, rel, s1, imp, cost, _, held = best
            grid.append(a)
            rel_flags.append(rel)
            hold_flags.append(held and not rel)
            imports.append(imp)
            cost_real += cost
            budget_left -= a
            s = s1
            stored_end.append(s)
        return {
            "grid": grid,
            "release": rel_flags,
            "hold": hold_flags,
            "imports": imports,
            "stored_end": stored_end,
            "cost": cost_real,
            "total": sum(grid),
        }

    def baseline(self, stored0: float) -> tuple[float, list[float]]:
        """Verhalten ohne Plan: keine Netzladung, Entladung immer freigegeben."""
        s = stored0
        cost = 0.0
        imports: list[float] = []
        for i in range(self.n):
            s, imp, _, c, _ = self.flow(s, 0.0, True, i)
            cost += c
            imports.append(imp)
        return cost, imports


def plan_price_charging(
    *,
    slot_hours: list[float],
    prices: list[float],
    consumption_kwh: list[float],
    pv_kwh: list[float],
    soc_pct: float,
    capacity_kwh: float,
    floor_pct: float,
    ceiling_pct: float,
    max_charge_kw: float,
    budget_kwh: float,
    max_discharge_kw: float | None = None,
    efficiency: float = 0.85,
    min_spread: float = 0.08,
    wear_eur_per_kwh: float = 0.0,
    feed_in_price: float = 0.08,
    consumption_safety_factor: float = 1.0,
    pv_factor: float = 1.0,
    step_kwh: float = 0.25,
) -> PricePlan:
    """Plant Netzladung und Entladesperre je Slot. Slot 0 ist der aktuelle (Rest-)Slot.

    ``consumption_kwh``/``pv_kwh`` sind erwartete Energien je Slot; der
    Verbrauch wird mit ``consumption_safety_factor`` (> 1 = konservativ), die
    PV mit ``pv_factor`` (< 1 = konservativ, z. B. P10/P50) skaliert.
    ``min_spread`` ist die mindestens geforderte Netto-Ersparnis in €/kWh
    je geladener Netz-kWh (nach Wirkungsgrad und Verschleiß).
    Energien am Horizontende haben keinen Restwert (konservativ).
    """
    n = len(slot_hours)
    if (
        n == 0
        or not (len(prices) == len(consumption_kwh) == len(pv_kwh) == n)
        or capacity_kwh <= 0
    ):
        return PricePlan(reason="Preisplan: unvollständige Eingangsdaten")
    if not 0.0 < efficiency <= 1.0:
        efficiency = 0.85

    net = [
        max(0.0, pv) * pv_factor - max(0.0, c) * consumption_safety_factor
        for pv, c in zip(pv_kwh, consumption_kwh)
    ]
    floor_kwh = capacity_kwh * max(0.0, floor_pct) / 100.0
    ceil_kwh = max(floor_kwh, capacity_kwh * min(100.0, ceiling_pct) / 100.0)
    stored0 = capacity_kwh * max(0.0, min(100.0, soc_pct)) / 100.0
    top_kwh = max(ceil_kwh, stored0)
    if max_discharge_kw is None:
        max_discharge_kw = max_charge_kw

    model = _Model(
        slot_hours=slot_hours,
        prices=prices,
        net_kwh=net,
        floor_kwh=floor_kwh,
        ceil_kwh=ceil_kwh,
        top_kwh=top_kwh,
        max_charge_kw=max_charge_kw,
        max_discharge_kw=max_discharge_kw,
        efficiency=efficiency,
        feed_in_price=feed_in_price,
        wear_eur_per_kwh=wear_eur_per_kwh,
        step_kwh=step_kwh,
    )
    budget = max(0.0, budget_kwh)
    base_cost, base_imports = model.baseline(stored0)

    # Lösung ohne Budgetdruck; reicht das Budget nicht, wird per Schattenpreis
    # (Strafe je geladener Netz-kWh) auf das Budget heruntergeregelt.
    penalty = min_spread
    result = model.forward(model.backward(penalty, budget), stored0, penalty, budget)
    if result["total"] > budget + _EPS:
        lo, hi = penalty, penalty + 1.0
        for _ in range(_BISECTION_ITERATIONS):
            mid = (lo + hi) / 2.0
            trial = model.forward(model.backward(mid, budget), stored0, mid, budget)
            if trial["total"] > budget + _EPS:
                lo = mid
            else:
                hi = mid
        result = model.forward(model.backward(hi, budget), stored0, hi, budget)

    grid = result["grid"]
    total = result["total"]
    saving_eur = base_cost - result["cost"]
    soc_trace = [s / capacity_kwh * 100.0 for s in result["stored_end"]]

    charge_now = grid[0] > _EPS
    target: float | None = None
    if charge_now:
        run_kwh = 0.0
        for g in grid:
            if g <= _EPS:
                break
            run_kwh += g
        target = min(
            ceiling_pct,
            soc_pct + run_kwh * efficiency / capacity_kwh * 100.0,
        )

    if total <= _EPS and not any(result["hold"]):
        reason = (
            f"Preisplan: keine Netzladung – keine Preisspanne ≥ "
            f"{min_spread * 100:.0f} ct/kWh nach Verlusten"
        )
    elif total <= _EPS:
        reason = (
            f"Preisplan: keine Netzladung, Entladung zeitweise gesperrt "
            f"(Energie für teure Slots halten), erwartete Ersparnis {saving_eur:.2f} €"
        )
    else:
        reason = (
            f"Preisplan: {total:.1f} kWh Netzladung geplant, "
            f"erwartete Ersparnis {saving_eur:.2f} €"
        )

    return PricePlan(
        grid_charge_kwh=grid,
        release=result["release"],
        hold_discharge=result["hold"],
        soc_pct=soc_trace,
        baseline_import_kwh=base_imports,
        planned_import_kwh=result["imports"],
        total_grid_charge_kwh=total,
        expected_saving_eur=saving_eur,
        charge_now=charge_now,
        hold_now=result["hold"][0],
        target_soc_pct=target,
        reason=reason,
    )
