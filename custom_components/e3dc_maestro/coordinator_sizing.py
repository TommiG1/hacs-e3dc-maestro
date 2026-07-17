"""Battery/PV sizing analysis and persistence."""
from __future__ import annotations

import logging

from homeassistant.util import dt as dt_util

from .battery_sizing import SizingAnalysisResult, SizingDataLoader, sweep_2d

_LOGGER = logging.getLogger(__name__)


class CoordinatorSizingMixin:
    @property
    def sizing_scenario_wr_upgrade(self) -> bool:
        """True when current slider PV value requires a WR upgrade."""
        try:
            from .const import CONF_INSTALLED_KWP, CONF_INVERTER_POWER, SIZING_INVERTER_UPGRADE_THRESHOLD
            opts = self.entry.options or self.entry.data or {}
            installed_kwp = float(opts.get(CONF_INSTALLED_KWP, 10.0))
            inverter_kw = float(opts.get(CONF_INVERTER_POWER, 10000)) / 1000.0
            total_kwp = installed_kwp + float(self.sizing_hypothetical_pv_kwp or 0.0)
            return (
                installed_kwp > 0
                and total_kwp > inverter_kw * SIZING_INVERTER_UPGRADE_THRESHOLD
            )
        except (TypeError, ValueError, KeyError) as err:
            _LOGGER.debug("Sizing WR-Upgrade-Check fehlgeschlagen: %s", err)
            return False


    async def async_run_sizing_analysis(self) -> None:
        """Run the full 2D sizing simulation in a thread-pool executor.

        Called by the 'Run Sizing Analysis' button entity.  Sets
        ``sizing_running`` during execution and updates ``sizing_analysis``
        when done.  Persists the result so it survives HA restarts.
        """
        if self.sizing_running:
            _LOGGER.warning("Sizing Advisor: Analyse läuft bereits, Aufruf ignoriert")
            return
        self.sizing_running = True
        self.async_update_listeners()
        try:
            opts = self.entry.options
            from .const import CONF_SIZING_ANALYSIS_DAYS, DEFAULT_SIZING_ANALYSIS_DAYS
            days = int(opts.get(CONF_SIZING_ANALYSIS_DAYS, DEFAULT_SIZING_ANALYSIS_DAYS))
            loader = SizingDataLoader(self.hass, opts)
            records = await loader.load_hourly_records(days)
            if not records:
                _LOGGER.warning("Sizing Advisor: keine historischen Daten – Analyse abgebrochen")
                return
            # Run CPU-heavy sweep in executor (keeps event loop free)
            result: SizingAnalysisResult = await self.hass.async_add_executor_job(
                sweep_2d, records, dict(opts)
            )
            self.sizing_analysis = result
            _LOGGER.info(
                "Sizing Advisor: Analyse abgeschlossen (%d Szenarien, %d Stunden)",
                len(result.battery_sizes_kwh) * len(result.pv_sizes_kwp),
                result.records_count,
            )
            await self._async_save_sizing()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Sizing Advisor: Analyse fehlgeschlagen: %s", err)
        finally:
            self.sizing_running = False
            self.async_update_listeners()


    async def _async_load_sizing(self) -> None:
        """Load persisted sizing result from disk."""
        try:
            data = await self._sizing_store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Sizing-Ergebnis konnte nicht geladen werden: %s", err)
            return
        if not isinstance(data, dict):
            return
        try:
            from datetime import datetime
            import math
            from .battery_sizing import (
                ScenarioResult, Recommendation, SizingAnalysisResult
            )

            def _load_scenario(d: dict) -> ScenarioResult:
                py = d.get("payback_years", math.inf)
                return ScenarioResult(
                    additional_kwh=d["additional_kwh"],
                    additional_kwp=d["additional_kwp"],
                    avoided_grid_import_kwh=d["avoided_grid_import_kwh"],
                    added_self_consumption_kwh=d.get("added_self_consumption_kwh", 0.0),
                    reduced_feed_in_kwh=d.get("reduced_feed_in_kwh", 0.0),
                    inverter_clipping_loss_kwh=d.get("inverter_clipping_loss_kwh", 0.0),
                    extra_pv_yield_kwh=d.get("extra_pv_yield_kwh", 0.0),
                    self_sufficiency_pct=d["self_sufficiency_pct"],
                    cycles_per_year=d.get("cycles_per_year", 0.0),
                    monthly_avoided_kwh=d.get("monthly_avoided_kwh", [0.0] * 12),
                    monthly_baseline_grid_in=d.get("monthly_baseline_grid_in", [0.0] * 12),
                    investment_eur=d["investment_eur"],
                    savings_eur_per_year=d["savings_eur_per_year"],
                    payback_years=math.inf if py is None else float(py),
                    inverter_upgrade_needed=d.get("inverter_upgrade_needed", False),
                )

            def _load_rec(d: dict | None) -> Recommendation | None:
                if not d:
                    return None
                py = d.get("payback_years")
                return Recommendation(
                    battery_kwh=d["battery_kwh"],
                    pv_kwp=d["pv_kwp"],
                    strategy=d["strategy"],
                    payback_years=float(py) if py is not None else None,
                    self_sufficiency_pct=d["self_sufficiency_pct"],
                    savings_eur_per_year=d["savings_eur_per_year"],
                    investment_eur=d["investment_eur"],
                    reason=d.get("reason"),
                )

            matrix_raw = data.get("matrix", [])
            matrix = [[_load_scenario(cell) for cell in row] for row in matrix_raw]
            computed_at_raw = data.get("computed_at")
            computed_at = (
                datetime.fromisoformat(computed_at_raw)
                if isinstance(computed_at_raw, str)
                else dt_util.utcnow()
            )
            self.sizing_analysis = SizingAnalysisResult(
                records_count=data.get("records_count", 0),
                analysis_days=data.get("analysis_days", 0),
                battery_sizes_kwh=data.get("battery_sizes_kwh", []),
                pv_sizes_kwp=data.get("pv_sizes_kwp", []),
                matrix=matrix,
                recommended_economic=_load_rec(data.get("recommended_economic")),
                recommended_technical=_load_rec(data.get("recommended_technical")),
                recommended_balanced=_load_rec(data.get("recommended_balanced")),
                baseline=_load_scenario(data["baseline"]) if "baseline" in data else matrix[0][0] if matrix and matrix[0] else None,  # type: ignore[arg-type]
                anomaly_rate=data.get("anomaly_rate", 0.0),
                computed_at=computed_at,
            )
            _LOGGER.info("Sizing Advisor: gespeicherte Analyse geladen (%s)", computed_at)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Sizing Advisor: gespeicherte Daten konnten nicht gelesen werden: %s", err)


    async def _async_save_sizing(self) -> None:
        """Persist sizing result to disk."""
        if self.sizing_analysis is None:
            return
        import math
        sa = self.sizing_analysis

        def _dump_scenario(r) -> dict:
            return {
                "additional_kwh": r.additional_kwh,
                "additional_kwp": r.additional_kwp,
                "avoided_grid_import_kwh": r.avoided_grid_import_kwh,
                "added_self_consumption_kwh": r.added_self_consumption_kwh,
                "reduced_feed_in_kwh": r.reduced_feed_in_kwh,
                "inverter_clipping_loss_kwh": r.inverter_clipping_loss_kwh,
                "extra_pv_yield_kwh": r.extra_pv_yield_kwh,
                "self_sufficiency_pct": r.self_sufficiency_pct,
                "cycles_per_year": r.cycles_per_year,
                "monthly_avoided_kwh": r.monthly_avoided_kwh,
                "monthly_baseline_grid_in": r.monthly_baseline_grid_in,
                "investment_eur": r.investment_eur,
                "savings_eur_per_year": r.savings_eur_per_year,
                "payback_years": None if r.payback_years == math.inf else r.payback_years,
                "inverter_upgrade_needed": r.inverter_upgrade_needed,
            }

        def _dump_rec(r) -> dict | None:
            if r is None:
                return None
            return {
                "battery_kwh": r.battery_kwh,
                "pv_kwp": r.pv_kwp,
                "strategy": r.strategy,
                "payback_years": r.payback_years,
                "self_sufficiency_pct": r.self_sufficiency_pct,
                "savings_eur_per_year": r.savings_eur_per_year,
                "investment_eur": r.investment_eur,
                "reason": r.reason,
            }

        try:
            await self._sizing_store.async_save({
                "records_count": sa.records_count,
                "analysis_days": sa.analysis_days,
                "battery_sizes_kwh": sa.battery_sizes_kwh,
                "pv_sizes_kwp": sa.pv_sizes_kwp,
                "matrix": [[_dump_scenario(cell) for cell in row] for row in sa.matrix],
                "recommended_economic": _dump_rec(sa.recommended_economic),
                "recommended_technical": _dump_rec(sa.recommended_technical),
                "recommended_balanced": _dump_rec(sa.recommended_balanced),
                "baseline": _dump_scenario(sa.baseline),
                "anomaly_rate": sa.anomaly_rate,
                "computed_at": sa.computed_at.isoformat(),
            })
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Sizing-Ergebnis konnte nicht gespeichert werden: %s", err)
