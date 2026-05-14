"""Battery & PV Sizing Advisor for E3DC Maestro.

Runs a historical replay simulation over HA long-term statistics to compute
how much grid import could have been avoided with additional battery capacity
and/or PV expansion.  Results drive three recommendation strategies:
  - Economic: fastest payback (minimum payback_years)
  - Technical: highest self-sufficiency (maximum autarky %)
  - Balanced:  Pareto-knee (elbow of investment vs. savings curve)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FEED_IN_LIMIT_PERCENT,
    CONF_INSTALLED_KWP,
    CONF_INVERTER_POWER,
    CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
    CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
    CONF_SIZING_BATTERY_PRICE_EUR_KWH,
    CONF_SIZING_BATTERY_STEP_KWH,
    CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH,
    CONF_SIZING_FEED_IN_PRICE_EUR_KWH,
    CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
    CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
    CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR,
    CONF_SIZING_HOUSE_ENERGY_SENSOR,
    CONF_SIZING_HOUSE_FROM_BALANCE,
    CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR,
    CONF_SIZING_MAX_BATTERY_SWEEP_KWH,
    CONF_SIZING_MAX_PV_EXPANSION_KWP,
    CONF_SIZING_PV_ENERGY_SENSOR,
    CONF_SIZING_PV_PRICE_EUR_PER_KWP,
    CONF_SIZING_PV_STEP_KWP,
    CONF_SIZING_ROUND_TRIP_EFFICIENCY,
    CONF_SIZING_WALLBOX_ENERGY_SENSOR,
    DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH,
    DEFAULT_SIZING_BATTERY_STEP_KWH,
    DEFAULT_SIZING_ELECTRICITY_PRICE,
    DEFAULT_SIZING_FEED_IN_PRICE,
    DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR,
    DEFAULT_SIZING_MAX_BATTERY_SWEEP_KWH,
    DEFAULT_SIZING_MAX_PV_EXPANSION_KWP,
    DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP,
    DEFAULT_SIZING_PV_STEP_KWP,
    DEFAULT_SIZING_ROUND_TRIP_EFFICIENCY,
    SIZING_C_RATE,
    SIZING_INVERTER_UPGRADE_THRESHOLD,
    SIZING_MAX_PAYBACK_YEARS,
)

_LOGGER = logging.getLogger(__name__)

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class HourlyRecord:
    """Energy flows for a single hour (kWh), all values ≥ 0."""

    timestamp: datetime
    pv_kwh: float
    house_kwh: float
    grid_in_kwh: float        # imported from grid
    grid_out_kwh: float       # exported to grid
    batt_charge_kwh: float
    batt_discharge_kwh: float
    wallbox_kwh: float
    hp_kwh: float
    anomaly: bool = False     # energy balance deviation > 5 %


@dataclass
class ScenarioResult:
    """Result for a single (additional_battery, additional_PV) scenario."""

    additional_kwh: float
    additional_kwp: float
    avoided_grid_import_kwh: float
    added_self_consumption_kwh: float
    reduced_feed_in_kwh: float
    inverter_clipping_loss_kwh: float
    extra_pv_yield_kwh: float
    self_sufficiency_pct: float
    cycles_per_year: float
    monthly_avoided_kwh: list[float]      # 12 months (Jan=0 … Dec=11)
    monthly_baseline_grid_in: list[float]  # baseline grid import per month
    investment_eur: float
    savings_eur_per_year: float
    payback_years: float                   # math.inf when not profitable
    inverter_upgrade_needed: bool


@dataclass
class Recommendation:
    """A recommended (battery, PV) combination."""

    battery_kwh: float
    pv_kwp: float
    strategy: str           # "economic" | "technical" | "balanced"
    payback_years: float | None
    self_sufficiency_pct: float
    savings_eur_per_year: float
    investment_eur: float
    reason: str | None = None


@dataclass
class SizingAnalysisResult:
    """Complete result of the 2D sizing analysis."""

    records_count: int
    analysis_days: int
    battery_sizes_kwh: list[float]
    pv_sizes_kwp: list[float]
    matrix: list[list[ScenarioResult]]    # [battery_idx][pv_idx]
    recommended_economic: Recommendation | None
    recommended_technical: Recommendation | None
    recommended_balanced: Recommendation | None
    baseline: ScenarioResult               # (0 kWh, 0 kWp) = status quo
    anomaly_rate: float                    # fraction of hours with anomaly
    computed_at: datetime


# ── Data loader ───────────────────────────────────────────────────────────────


class SizingDataLoader:
    """Load hourly energy data from HA recorder long-term statistics."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self._hass = hass
        self._opts = options

    async def load_hourly_records(self, days: int) -> list[HourlyRecord]:
        """Return a list of HourlyRecord for the past *days* days.

        Uses ``statistics_during_period`` with ``period="hour"`` and
        ``types={"sum"}`` (cumulative total) for *total_increasing* energy
        sensors.  Hourly kWh values are derived from consecutive differences.
        """
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
        except Exception as err:
            _LOGGER.error("Recorder nicht verfügbar: %s", err)
            return []

        now = dt_util.utcnow()
        # +2 hours margin so we always have a prior row for the delta of the first hour
        start = now - timedelta(days=days) - timedelta(hours=2)

        # Collect all entity IDs
        # CONF_SIZING_PV_ENERGY_SENSOR may be a list (multi-inverter) or a legacy string
        _pv_val = self._opts.get(CONF_SIZING_PV_ENERGY_SENSOR)
        pv_entity_ids: list[str] = (
            _pv_val if isinstance(_pv_val, list) else ([_pv_val] if _pv_val else [])
        )
        required_keys = [
            CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR,
            CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR,
            CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR,
            CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR,
        ]
        optional_keys = [
            CONF_SIZING_HOUSE_ENERGY_SENSOR,  # optional: derived from balance if absent
            CONF_SIZING_WALLBOX_ENERGY_SENSOR,
            CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR,
        ]
        entity_ids: set[str] = set(pv_entity_ids)
        for key in required_keys:
            eid = self._opts.get(key)
            if eid:
                entity_ids.add(eid)
        for key in optional_keys:
            eid = self._opts.get(key)
            if eid:
                entity_ids.add(eid)

        required_count = len(required_keys) + (1 if pv_entity_ids else 0)
        if not pv_entity_ids or len(entity_ids) < len(required_keys) + 1:
            _LOGGER.warning(
                "Sizing Advisor: nicht alle Pflicht-Sensoren konfiguriert. "
                "PV: %s, weitere: %s/%s", pv_entity_ids, len(entity_ids), required_count
            )

        if not entity_ids:
            return []

        try:
            raw: dict[str, list[dict[str, Any]]] = await get_instance(
                self._hass
            ).async_add_executor_job(
                statistics_during_period,
                self._hass,
                start,
                now,
                entity_ids,
                "hour",
                None,
                {"sum"},
            )
        except Exception as err:
            _LOGGER.error("Sizing Advisor: Recorder-Abfrage fehlgeschlagen: %s", err)
            return []

        def _key(k: str) -> list[dict[str, Any]]:
            eid = self._opts.get(k, "")
            return (raw or {}).get(eid, [])

        def _unit_factor(eid: str | None) -> float:
            """Return multiplier to convert the sensor's native energy unit to kWh."""
            if not eid:
                return 1.0
            state = self._hass.states.get(eid)
            unit = (state.attributes.get("unit_of_measurement") if state else "") or ""
            unit_l = unit.strip().lower()
            if unit_l == "wh":
                return 0.001
            if unit_l == "mwh":
                return 1000.0
            if unit_l == "gwh":
                return 1_000_000.0
            # kWh or unknown → assume kWh (no conversion)
            if unit_l and unit_l != "kwh":
                _LOGGER.warning(
                    "Sizing Advisor: Sensor %s hat unbekannte Einheit '%s' – nehme kWh an.",
                    eid, unit,
                )
            return 1.0

        def _to_delta_map(rows: list[dict[str, Any]], factor: float = 1.0) -> dict[datetime, float]:
            """Convert cumulative sum rows to hourly delta map keyed by start time."""
            result: dict[datetime, float] = {}
            prev_sum: float | None = None
            for row in rows:
                s = row.get("sum")
                if s is None:
                    prev_sum = None
                    continue
                s = float(s)
                ts = row.get("start")
                if ts is None:
                    prev_sum = s
                    continue
                if isinstance(ts, str):
                    try:
                        from datetime import datetime as _dt
                        ts = _dt.fromisoformat(ts)
                    except Exception:
                        prev_sum = s
                        continue
                elif isinstance(ts, (int, float)):
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        ts = _dt.fromtimestamp(float(ts), tz=_tz.utc)
                    except Exception:
                        prev_sum = s
                        continue
                if not isinstance(ts, datetime):
                    prev_sum = s
                    continue
                # Ensure tz-aware (assume UTC if naive)
                if ts.tzinfo is None:
                    from datetime import timezone as _tz
                    ts = ts.replace(tzinfo=_tz.utc)
                if prev_sum is not None:
                    delta = s - prev_sum
                    # Negative delta = meter reset or correction; treat as 0
                    result[ts] = max(0.0, delta) * factor
                prev_sum = s
            return result

        # Build PV delta map by summing all configured PV inverters per timestamp
        # (each inverter individually converted to kWh based on its unit).
        def _merged_pv_map() -> dict[datetime, float]:
            merged: dict[datetime, float] = {}
            for eid in pv_entity_ids:
                factor = _unit_factor(eid)
                for ts, val in _to_delta_map((raw or {}).get(eid, []), factor).items():
                    merged[ts] = merged.get(ts, 0.0) + val
            return merged

        pv_map = _merged_pv_map()
        house_rows = _key(CONF_SIZING_HOUSE_ENERGY_SENSOR)
        grid_in_rows = _key(CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR)
        grid_out_rows = _key(CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR)
        batt_c_rows = _key(CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR)
        batt_d_rows = _key(CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR)
        wb_rows = _key(CONF_SIZING_WALLBOX_ENERGY_SENSOR)
        hp_rows = _key(CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR)

        house_map = _to_delta_map(house_rows, _unit_factor(self._opts.get(CONF_SIZING_HOUSE_ENERGY_SENSOR)))
        grid_in_map = _to_delta_map(grid_in_rows, _unit_factor(self._opts.get(CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR)))
        grid_out_map = _to_delta_map(grid_out_rows, _unit_factor(self._opts.get(CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR)))
        batt_c_map = _to_delta_map(batt_c_rows, _unit_factor(self._opts.get(CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR)))
        batt_d_map = _to_delta_map(batt_d_rows, _unit_factor(self._opts.get(CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR)))
        wb_map = _to_delta_map(wb_rows, _unit_factor(self._opts.get(CONF_SIZING_WALLBOX_ENERGY_SENSOR)))
        hp_map = _to_delta_map(hp_rows, _unit_factor(self._opts.get(CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR)))

        # If no house-sensor data is available, derive consumption from the
        # energy balance: house = pv + grid_in + batt_d - grid_out - batt_c
        # In that case skip the imbalance-anomaly check (it would always pass).
        force_balance = bool(self._opts.get(CONF_SIZING_HOUSE_FROM_BALANCE, False))
        derive_house = force_balance or not house_map

        # Plausibility logging: sum per sensor over the analysis window.
        sums = {
            "PV": sum(pv_map.values()),
            "Grid-Import": sum(grid_in_map.values()),
            "Grid-Export": sum(grid_out_map.values()),
            "Batt-Charge": sum(batt_c_map.values()),
            "Batt-Discharge": sum(batt_d_map.values()),
            "House": sum(house_map.values()),
        }
        _LOGGER.info(
            "Sizing Advisor: Sensorsummen über %d Tage – %s (derive_house=%s)",
            days, sums, derive_house,
        )
        # Detect dead sensors: in derive_house mode a missing grid_in causes
        # house = pv - g_out, which yields 100 %% autarky regardless of reality.
        # Refuse to build records in that pathological case.
        if derive_house and sums["Grid-Import"] <= 0.0:
            _LOGGER.error(
                "Sizing Advisor: Grid-Import-Sensor liefert 0 kWh über %d Tage. "
                "Ohne Netzbezugs-Daten ist im 'Hauslast-aus-Bilanz'-Modus keine "
                "valide Autarkie-Berechnung möglich. Prüfe den Sensor in den "
                "Sizing-Advisor-Einstellungen.",
                days,
            )
            return []
        for label in ("Grid-Export", "Batt-Charge", "Batt-Discharge"):
            if sums[label] <= 0.0:
                _LOGGER.warning(
                    "Sizing Advisor: Sensor für '%s' liefert 0 kWh – KPIs könnten "
                    "unzuverlässig sein.", label,
                )

        # Use PV timestamps as the primary time axis (every sensor should align)
        all_ts = sorted(pv_map.keys())
        # Restrict to the actual requested window
        cutoff = now - timedelta(days=days)
        all_ts = [t for t in all_ts if t >= cutoff]

        if not all_ts:
            _LOGGER.warning("Sizing Advisor: keine Statistikdaten für die letzten %d Tage", days)
            return []

        records: list[HourlyRecord] = []
        anomaly_count = 0

        for ts in all_ts:
            pv = pv_map.get(ts, 0.0)
            g_in = grid_in_map.get(ts, 0.0)
            g_out = grid_out_map.get(ts, 0.0)
            b_c = batt_c_map.get(ts, 0.0)
            b_d = batt_d_map.get(ts, 0.0)
            wb = wb_map.get(ts, 0.0)
            hp = hp_map.get(ts, 0.0)

            if derive_house:
                # Derive house from balance; anomaly flag not meaningful here
                house = max(0.0, pv + g_in + b_d - g_out - b_c)
                anomaly = False
            else:
                house = house_map.get(ts, 0.0)
                # Energy balance check: generation + import ≈ consumption + export
                # (within 5 % of house load, with a 50 Wh floor to avoid false flags at night)
                generation = pv + b_d + g_in
                consumption = house + b_c + g_out
                imbalance = abs(generation - consumption)
                threshold = max(0.05 * house, 0.05)
                anomaly = imbalance > threshold

            if anomaly:
                anomaly_count += 1

            records.append(
                HourlyRecord(
                    timestamp=ts,
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
            )

        anomaly_rate = anomaly_count / len(records) if records else 0.0
        _LOGGER.info(
            "Sizing Advisor: %d Stunden geladen, %.1f%% Energiebilanz-Anomalien",
            len(records), anomaly_rate * 100,
        )
        return records


# ── Simulation engine ─────────────────────────────────────────────────────────


def simulate_scenario(
    records: list[HourlyRecord],
    additional_kwh: float,
    additional_kwp: float,
    installed_kwp: float,
    inverter_power_w: float,
    feed_in_limit_pct: float,
    electricity_price: float,
    feed_in_price: float,
    battery_price_per_kwh: float,
    pv_price_per_kwp: float,
    inverter_upgrade_price: float,
    round_trip_efficiency: float,
) -> ScenarioResult:
    """Simulate one (battery, PV) scenario over all records.

    The virtual extra battery operates in parallel with the existing system:
    - Charged from surplus (grid_out + extra PV) up to C_rate limit
    - Discharged to cover grid import up to C_rate limit
    - Round-trip efficiency applied as √η per direction (charge AND discharge)

    PV expansion is modelled by proportional scaling of measured PV output,
    then capped by the inverter rating (Wechselrichter-Clipping).
    """
    if not records:
        return _zero_scenario(
            additional_kwh, additional_kwp,
            battery_price_per_kwh, pv_price_per_kwp, inverter_upgrade_price,
            installed_kwp, inverter_power_w,
        )

    sqrt_eta = math.sqrt(max(round_trip_efficiency, 0.5))
    c_rate_kwh = SIZING_C_RATE * additional_kwh         # max kWh per hour

    # Inverter upgrade needed?
    inverter_kw = inverter_power_w / 1000.0
    total_kwp = installed_kwp + additional_kwp
    inverter_upgrade_needed = (
        installed_kwp > 0
        and total_kwp > inverter_kw * SIZING_INVERTER_UPGRADE_THRESHOLD
    )

    # Investment
    investment = (
        additional_kwh * battery_price_per_kwh
        + additional_kwp * pv_price_per_kwp
        + (inverter_upgrade_price if inverter_upgrade_needed else 0.0)
    )

    # Effective inverter cap: if upgrading, the WR becomes large enough for the new PV
    effective_inverter_kw = total_kwp if inverter_upgrade_needed else inverter_kw

    # Scale factor for PV
    pv_scale = (total_kwp / installed_kwp) if installed_kwp > 0 else 1.0

    # FiT limit for the extended system (kWh/h at peak)
    # Applied as a cap on net export (grid_out) – energy above this is curtailed
    # unless absorbed by the (virtual + real) battery.
    # We model FiT as: net export after battery ≤ fit_limit_kwh_per_hour
    fit_limit_kwh = total_kwp * feed_in_limit_pct / 100.0

    virt_soc: float = 0.0
    total_avoided: float = 0.0
    total_reduced_feedin: float = 0.0
    total_clipping: float = 0.0
    total_extra_pv: float = 0.0
    total_charged_cycles: float = 0.0    # for cycles/year
    total_house: float = 0.0
    total_new_grid_in: float = 0.0
    delta_export_total: float = 0.0

    monthly_avoided: list[float] = [0.0] * 12
    monthly_baseline_gin: list[float] = [0.0] * 12

    for rec in records:
        month_idx = rec.timestamp.month - 1
        total_house += rec.house_kwh
        monthly_baseline_gin[month_idx] += rec.grid_in_kwh

        # ── Step 1: Scale PV (proportional, then WR-clip) ──────────────────
        if installed_kwp > 0 and additional_kwp > 0:
            pv_scaled = rec.pv_kwh * pv_scale
            pv_capped = min(pv_scaled, effective_inverter_kw)
            clipping = max(0.0, pv_scaled - pv_capped)
            extra_pv = max(0.0, pv_capped - rec.pv_kwh)
        else:
            pv_capped = rec.pv_kwh
            clipping = 0.0
            extra_pv = 0.0

        total_clipping += clipping
        total_extra_pv += extra_pv

        # ── Step 2: Net energy balance with extended PV (pre-virtual-batt) ──
        # net = (grid_out - grid_in) + extra_pv
        #   > 0: surplus going to grid  (can charge virtual batt)
        #   < 0: deficit from grid      (virtual batt can help)
        old_net = rec.grid_out_kwh - rec.grid_in_kwh
        net = old_net + extra_pv

        # ── Step 3: Virtual battery ─────────────────────────────────────────
        if additional_kwh == 0 and additional_kwp == 0:
            # Null-Szenario = Baseline: keine Veränderung
            reduced_feedin = 0.0
            post_grid_in = rec.grid_in_kwh
            post_grid_out = rec.grid_out_kwh
        elif additional_kwh > 0:
            if net >= 0:
                # Surplus → charge virtual battery
                available = net                   # includes extra PV and original surplus
                charge = min(available, c_rate_kwh, additional_kwh - virt_soc)
                charge = max(0.0, charge)
                stored = charge * sqrt_eta
                virt_soc += stored
                total_charged_cycles += stored
                reduced_feedin = charge           # this export goes to battery instead
                post_grid_in = 0.0
                post_grid_out = net - charge
            else:
                # Deficit → discharge virtual battery
                deficit = -net
                discharge = min(deficit, c_rate_kwh, virt_soc)
                discharge = max(0.0, discharge)
                delivered = discharge * sqrt_eta
                virt_soc -= discharge
                reduced_feedin = 0.0
                post_grid_in = deficit - delivered
                post_grid_out = 0.0
        else:
            # No virtual battery
            reduced_feedin = 0.0
            post_grid_in = max(0.0, -net)
            post_grid_out = max(0.0, net)

        # ── Step 4: FiT-limit on post-battery export ────────────────────────
        # If post_grid_out exceeds the extended FiT limit and there's still
        # space in the virtual battery, absorb the excess.
        if additional_kwh > 0 and post_grid_out > fit_limit_kwh:
            fit_excess = post_grid_out - fit_limit_kwh
            absorb = min(fit_excess, c_rate_kwh - (additional_kwh - virt_soc - 1e-9), additional_kwh - virt_soc)
            # c_rate check: remaining capacity for this hour
            absorb = max(0.0, absorb)
            stored2 = absorb * sqrt_eta
            virt_soc += stored2
            total_charged_cycles += stored2
            reduced_feedin += absorb
            post_grid_out -= absorb

        # ── Step 5: Accumulate ──────────────────────────────────────────────
        avoided_this_hour = rec.grid_in_kwh - post_grid_in  # positive = avoided import
        avoided_this_hour = max(0.0, avoided_this_hour)
        delta_export = post_grid_out - rec.grid_out_kwh       # positive = more export

        total_avoided += avoided_this_hour
        total_reduced_feedin += max(0.0, reduced_feedin)
        total_new_grid_in += post_grid_in
        delta_export_total += delta_export
        monthly_avoided[month_idx] += avoided_this_hour

    # ── Annualise ────────────────────────────────────────────────────────────
    actual_days = len(records) / 24.0
    scale_to_year = 365.0 / max(actual_days, 1.0)

    avoided_annual = total_avoided * scale_to_year
    extra_pv_annual = total_extra_pv * scale_to_year
    clipping_annual = total_clipping * scale_to_year
    reduced_feedin_annual = total_reduced_feedin * scale_to_year
    delta_export_annual = delta_export_total * scale_to_year
    cycles_per_year = (total_charged_cycles / max(additional_kwh, 0.001)) * scale_to_year if additional_kwh > 0 else 0.0

    monthly_avoided_annual = [v * scale_to_year for v in monthly_avoided]
    monthly_baseline_gin_annual = [v * scale_to_year for v in monthly_baseline_gin]

    # Self-sufficiency with extended system
    total_new_grid_in_annual = total_new_grid_in * scale_to_year
    total_house_annual = total_house * scale_to_year
    if total_house_annual > 0:
        self_suff = max(0.0, min(100.0, (total_house_annual - total_new_grid_in_annual) / total_house_annual * 100.0))
    else:
        self_suff = 0.0

    # Financial savings
    # - avoided import saves electricity costs
    # - delta in export earnings (more export from extra PV, less from reduced feed-in)
    savings = (
        avoided_annual * electricity_price
        + delta_export_annual * feed_in_price
    )

    payback = (investment / savings) if savings > 1e-6 else math.inf

    return ScenarioResult(
        additional_kwh=additional_kwh,
        additional_kwp=additional_kwp,
        avoided_grid_import_kwh=round(avoided_annual, 1),
        added_self_consumption_kwh=round(extra_pv_annual - reduced_feedin_annual, 1),
        reduced_feed_in_kwh=round(reduced_feedin_annual, 1),
        inverter_clipping_loss_kwh=round(clipping_annual, 1),
        extra_pv_yield_kwh=round(extra_pv_annual, 1),
        self_sufficiency_pct=round(self_suff, 1),
        cycles_per_year=round(cycles_per_year, 1),
        monthly_avoided_kwh=[round(v, 1) for v in monthly_avoided_annual],
        monthly_baseline_grid_in=[round(v, 1) for v in monthly_baseline_gin_annual],
        investment_eur=round(investment, 0),
        savings_eur_per_year=round(savings, 1),
        payback_years=round(payback, 1) if payback != math.inf else math.inf,
        inverter_upgrade_needed=inverter_upgrade_needed,
    )


def _zero_scenario(
    additional_kwh: float,
    additional_kwp: float,
    battery_price: float,
    pv_price: float,
    inverter_upgrade_price: float,
    installed_kwp: float,
    inverter_power_w: float,
) -> ScenarioResult:
    inverter_kw = inverter_power_w / 1000.0
    total_kwp = installed_kwp + additional_kwp
    upgrade = installed_kwp > 0 and total_kwp > inverter_kw * SIZING_INVERTER_UPGRADE_THRESHOLD
    inv = (
        additional_kwh * battery_price
        + additional_kwp * pv_price
        + (inverter_upgrade_price if upgrade else 0.0)
    )
    return ScenarioResult(
        additional_kwh=additional_kwh, additional_kwp=additional_kwp,
        avoided_grid_import_kwh=0.0, added_self_consumption_kwh=0.0,
        reduced_feed_in_kwh=0.0, inverter_clipping_loss_kwh=0.0,
        extra_pv_yield_kwh=0.0, self_sufficiency_pct=0.0,
        cycles_per_year=0.0, monthly_avoided_kwh=[0.0] * 12,
        monthly_baseline_grid_in=[0.0] * 12,
        investment_eur=round(inv, 0),
        savings_eur_per_year=0.0, payback_years=math.inf,
        inverter_upgrade_needed=upgrade,
    )


def sweep_2d(
    records: list[HourlyRecord],
    options: dict[str, Any],
) -> SizingAnalysisResult:
    """Run the full 2D sweep and return a :class:`SizingAnalysisResult`.

    Battery sweep: 0 … max_battery_kwh in steps of battery_step_kwh
    PV sweep:      0 … max_pv_kwp in steps of pv_step_kwp
    """
    installed_kwp: float = float(options.get(CONF_INSTALLED_KWP, 10.0))
    inverter_power_w: float = float(options.get(CONF_INVERTER_POWER, 12000))
    feed_in_limit_pct: float = float(options.get(CONF_FEED_IN_LIMIT_PERCENT, 70.0))
    elec_price: float = float(options.get(CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH, DEFAULT_SIZING_ELECTRICITY_PRICE))
    fit_price: float = float(options.get(CONF_SIZING_FEED_IN_PRICE_EUR_KWH, DEFAULT_SIZING_FEED_IN_PRICE))
    batt_price: float = float(options.get(CONF_SIZING_BATTERY_PRICE_EUR_KWH, DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH))
    pv_price: float = float(options.get(CONF_SIZING_PV_PRICE_EUR_PER_KWP, DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP))
    inv_upgrade_price: float = float(options.get(CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR, DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR))
    eta: float = float(options.get(CONF_SIZING_ROUND_TRIP_EFFICIENCY, DEFAULT_SIZING_ROUND_TRIP_EFFICIENCY))
    max_batt: float = float(options.get(CONF_SIZING_MAX_BATTERY_SWEEP_KWH, DEFAULT_SIZING_MAX_BATTERY_SWEEP_KWH))
    batt_step: float = float(options.get(CONF_SIZING_BATTERY_STEP_KWH, DEFAULT_SIZING_BATTERY_STEP_KWH))
    max_pv: float = float(options.get(CONF_SIZING_MAX_PV_EXPANSION_KWP, DEFAULT_SIZING_MAX_PV_EXPANSION_KWP))
    pv_step: float = float(options.get(CONF_SIZING_PV_STEP_KWP, DEFAULT_SIZING_PV_STEP_KWP))

    # Build sweep vectors (always include 0)
    batt_step = max(batt_step, 0.5)
    pv_step = max(pv_step, 0.5)
    battery_sizes = _sweep_vector(0.0, max_batt, batt_step)
    pv_sizes = _sweep_vector(0.0, max_pv, pv_step)

    anomaly_count = sum(1 for r in records if r.anomaly)
    anomaly_rate = anomaly_count / len(records) if records else 0.0
    analysis_days = len(records) // 24

    _LOGGER.info(
        "Sizing Advisor: Sweep %dx%d Szenarien über %d Stunden",
        len(battery_sizes), len(pv_sizes), len(records),
    )

    matrix: list[list[ScenarioResult]] = []
    for b_kwh in battery_sizes:
        row: list[ScenarioResult] = []
        for p_kwp in pv_sizes:
            result = simulate_scenario(
                records=records,
                additional_kwh=b_kwh,
                additional_kwp=p_kwp,
                installed_kwp=installed_kwp,
                inverter_power_w=inverter_power_w,
                feed_in_limit_pct=feed_in_limit_pct,
                electricity_price=elec_price,
                feed_in_price=fit_price,
                battery_price_per_kwh=batt_price,
                pv_price_per_kwp=pv_price,
                inverter_upgrade_price=inv_upgrade_price,
                round_trip_efficiency=eta,
            )
            row.append(result)
        matrix.append(row)
        _LOGGER.debug("Sizing Advisor: Akku %.1f kWh – fertig", b_kwh)

    baseline = matrix[0][0]

    rec_eco, rec_tech, rec_bal = _find_recommendations(battery_sizes, pv_sizes, matrix)

    return SizingAnalysisResult(
        records_count=len(records),
        analysis_days=analysis_days,
        battery_sizes_kwh=battery_sizes,
        pv_sizes_kwp=pv_sizes,
        matrix=matrix,
        recommended_economic=rec_eco,
        recommended_technical=rec_tech,
        recommended_balanced=rec_bal,
        baseline=baseline,
        anomaly_rate=round(anomaly_rate, 3),
        computed_at=dt_util.utcnow(),
    )


def _sweep_vector(start: float, stop: float, step: float) -> list[float]:
    """Generate inclusive sweep from *start* to *stop* in *step* increments."""
    result: list[float] = []
    v = start
    while v <= stop + 1e-9:
        result.append(round(v, 3))
        v += step
    return result


def _find_recommendations(
    battery_sizes: list[float],
    pv_sizes: list[float],
    matrix: list[list[ScenarioResult]],
) -> tuple[Recommendation | None, Recommendation | None, Recommendation | None]:
    """Derive economic, technical and balanced recommendations from the matrix."""
    all_results: list[ScenarioResult] = [r for row in matrix for r in row]

    # ── Economic: minimum payback_years (ignoring infinite / no-data) ────────
    eco = _find_economic(all_results)

    # ── Technical: maximum self_sufficiency_pct, tie-break by investment ─────
    tech = _find_technical(all_results)

    # ── Balanced: Pareto-knee on (investment, savings) front ────────────────
    bal = _find_balanced(all_results)

    return eco, tech, bal


def _make_recommendation(r: ScenarioResult, strategy: str, reason: str | None = None) -> Recommendation:
    return Recommendation(
        battery_kwh=r.additional_kwh,
        pv_kwp=r.additional_kwp,
        strategy=strategy,
        payback_years=r.payback_years if r.payback_years != math.inf else None,
        self_sufficiency_pct=r.self_sufficiency_pct,
        savings_eur_per_year=r.savings_eur_per_year,
        investment_eur=r.investment_eur,
        reason=reason,
    )


def _find_economic(all_results: list[ScenarioResult]) -> Recommendation | None:
    viable = [r for r in all_results if r.payback_years != math.inf and r.payback_years <= SIZING_MAX_PAYBACK_YEARS and r.investment_eur > 0]
    if not viable:
        return None
    best = min(viable, key=lambda r: r.payback_years)
    return _make_recommendation(best, "economic")


def _find_technical(all_results: list[ScenarioResult]) -> Recommendation | None:
    candidates = [r for r in all_results if r.investment_eur > 0]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: (r.self_sufficiency_pct, -r.investment_eur))
    return _make_recommendation(best, "technical")


def _find_balanced(all_results: list[ScenarioResult]) -> Recommendation | None:
    """Find the Pareto-knee on the (investment, savings) front."""
    # Only consider scenarios that actually cost something and provide some saving
    candidates = [
        r for r in all_results
        if r.investment_eur > 0 and r.savings_eur_per_year > 0
    ]
    if not candidates:
        # Fall back: just find best ROI
        feasible = [r for r in all_results if r.investment_eur > 0 and r.savings_eur_per_year > 0]
        if not feasible:
            return None
        best = max(feasible, key=lambda r: r.savings_eur_per_year / r.investment_eur)
        return _make_recommendation(best, "balanced", reason="best_roi_fallback")

    pareto = _pareto_front(candidates)
    if not pareto:
        return None
    knee = _pareto_knee(pareto)
    return _make_recommendation(knee, "balanced")


def _pareto_front(results: list[ScenarioResult]) -> list[ScenarioResult]:
    """Return non-dominated solutions (minimise investment, maximise savings)."""
    pareto: list[ScenarioResult] = []
    for candidate in results:
        dominated = any(
            other.investment_eur <= candidate.investment_eur
            and other.savings_eur_per_year >= candidate.savings_eur_per_year
            and (
                other.investment_eur < candidate.investment_eur
                or other.savings_eur_per_year > candidate.savings_eur_per_year
            )
            for other in results
            if other is not candidate
        )
        if not dominated:
            pareto.append(candidate)
    return sorted(pareto, key=lambda r: r.investment_eur)


def _pareto_knee(pareto: list[ScenarioResult]) -> ScenarioResult:
    """Return the elbow point (maximum perpendicular distance to diagonal)."""
    if len(pareto) == 1:
        return pareto[0]

    x1, y1 = pareto[0].investment_eur, pareto[0].savings_eur_per_year
    x2, y2 = pareto[-1].investment_eur, pareto[-1].savings_eur_per_year
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return pareto[0]

    best_dist = -1.0
    best = pareto[0]
    for r in pareto:
        # Signed perpendicular distance from point (rx, ry) to line (p1)→(p2)
        d = abs(dy * r.investment_eur - dx * r.savings_eur_per_year + x2 * y1 - y2 * x1) / length
        if d > best_dist:
            best_dist = d
            best = r
    return best


# ── Interpolation helper ──────────────────────────────────────────────────────


def interpolate_result(
    analysis: SizingAnalysisResult,
    battery_kwh: float,
    pv_kwp: float,
) -> ScenarioResult | None:
    """Bilinear interpolation of scenario results for arbitrary slider values.

    Returns *None* when the analysis has no data.
    """
    if not analysis or not analysis.matrix:
        return None

    bs = analysis.battery_sizes_kwh
    ps = analysis.pv_sizes_kwp

    # Clamp to sweep range
    battery_kwh = max(bs[0], min(bs[-1], battery_kwh))
    pv_kwp = max(ps[0], min(ps[-1], pv_kwp))

    # Find bounding indices
    bi = _find_lower_idx(bs, battery_kwh)
    pi = _find_lower_idx(ps, pv_kwp)
    bi1 = min(bi + 1, len(bs) - 1)
    pi1 = min(pi + 1, len(ps) - 1)

    # Interpolation weights
    db = bs[bi1] - bs[bi]
    dp = ps[pi1] - ps[pi]
    tb = (battery_kwh - bs[bi]) / db if db > 1e-9 else 0.0
    tp = (pv_kwp - ps[pi]) / dp if dp > 1e-9 else 0.0

    r00 = analysis.matrix[bi][pi]
    r01 = analysis.matrix[bi][pi1]
    r10 = analysis.matrix[bi1][pi]
    r11 = analysis.matrix[bi1][pi1]

    def _lerp(a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    def _bilerp(v00: float, v01: float, v10: float, v11: float) -> float:
        return _lerp(_lerp(v00, v01, tp), _lerp(v10, v11, tp), tb)

    payback_raw = _bilerp(
        _finite(r00.payback_years), _finite(r01.payback_years),
        _finite(r10.payback_years), _finite(r11.payback_years),
    )

    # Compute investment (not interpolated – exact formula)
    from .const import SIZING_INVERTER_UPGRADE_THRESHOLD
    inverter_kw = 12.0  # placeholder; sensor can use options directly
    upgrade = (analysis.baseline.additional_kwh == 0)  # always false for baseline

    monthly_avoided = [
        round(_bilerp(
            r00.monthly_avoided_kwh[m], r01.monthly_avoided_kwh[m],
            r10.monthly_avoided_kwh[m], r11.monthly_avoided_kwh[m],
        ), 1)
        for m in range(12)
    ]
    monthly_gin = [
        round(_bilerp(
            r00.monthly_baseline_grid_in[m], r01.monthly_baseline_grid_in[m],
            r10.monthly_baseline_grid_in[m], r11.monthly_baseline_grid_in[m],
        ), 1)
        for m in range(12)
    ]

    return ScenarioResult(
        additional_kwh=battery_kwh,
        additional_kwp=pv_kwp,
        avoided_grid_import_kwh=round(_bilerp(
            r00.avoided_grid_import_kwh, r01.avoided_grid_import_kwh,
            r10.avoided_grid_import_kwh, r11.avoided_grid_import_kwh,
        ), 1),
        added_self_consumption_kwh=round(_bilerp(
            r00.added_self_consumption_kwh, r01.added_self_consumption_kwh,
            r10.added_self_consumption_kwh, r11.added_self_consumption_kwh,
        ), 1),
        reduced_feed_in_kwh=round(_bilerp(
            r00.reduced_feed_in_kwh, r01.reduced_feed_in_kwh,
            r10.reduced_feed_in_kwh, r11.reduced_feed_in_kwh,
        ), 1),
        inverter_clipping_loss_kwh=round(_bilerp(
            r00.inverter_clipping_loss_kwh, r01.inverter_clipping_loss_kwh,
            r10.inverter_clipping_loss_kwh, r11.inverter_clipping_loss_kwh,
        ), 1),
        extra_pv_yield_kwh=round(_bilerp(
            r00.extra_pv_yield_kwh, r01.extra_pv_yield_kwh,
            r10.extra_pv_yield_kwh, r11.extra_pv_yield_kwh,
        ), 1),
        self_sufficiency_pct=round(_bilerp(
            r00.self_sufficiency_pct, r01.self_sufficiency_pct,
            r10.self_sufficiency_pct, r11.self_sufficiency_pct,
        ), 1),
        cycles_per_year=round(_bilerp(
            r00.cycles_per_year, r01.cycles_per_year,
            r10.cycles_per_year, r11.cycles_per_year,
        ), 1),
        monthly_avoided_kwh=monthly_avoided,
        monthly_baseline_grid_in=monthly_gin,
        investment_eur=round(_bilerp(
            r00.investment_eur, r01.investment_eur,
            r10.investment_eur, r11.investment_eur,
        ), 0),
        savings_eur_per_year=round(_bilerp(
            r00.savings_eur_per_year, r01.savings_eur_per_year,
            r10.savings_eur_per_year, r11.savings_eur_per_year,
        ), 1),
        payback_years=round(payback_raw, 1) if payback_raw < 999 else math.inf,
        inverter_upgrade_needed=r11.inverter_upgrade_needed,  # conservative
    )


def _find_lower_idx(vec: list[float], val: float) -> int:
    """Return index of the largest element ≤ val."""
    for i in range(len(vec) - 1, -1, -1):
        if vec[i] <= val + 1e-9:
            return i
    return 0


def _finite(v: float) -> float:
    return v if v != math.inf else 999.0
