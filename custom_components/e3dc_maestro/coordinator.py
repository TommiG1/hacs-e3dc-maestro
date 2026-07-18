"""DataUpdateCoordinator for E3DC Maestro.

Polls configured sensor entities, runs the rule engine, and calls
e3dc_rscp services when the decision changes (debounced).
Handles Watchdog / Failsafe / Master-Switch off transitions.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .battery_sizing import SizingAnalysisResult
from .const import (
    CONF_BATTERY_CHARGED_TODAY_SENSOR,
    CONF_BATTERY_DISCHARGED_TODAY_SENSOR,
    CONF_CURTAILMENT_ACTIVATION_W,
    CONF_CURTAILMENT_RELEASE_W,
    CONF_DYNAMIC_TARIFF_ENABLED,
    CONF_HOUSE_POWER_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CURTAILMENT_ACTIVATION_W,
    DEFAULT_CURTAILMENT_RELEASE_W,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EWMA_JUMP_THRESHOLD_W,
    EWMA_TAU_S,
    PHASE_CURTAILMENT_GUARD,
    PHASE_EMERGENCY,
    PHASE_FEED_IN_LIMIT,
    PHASE_FORCE_DISCHARGE,
    PHASE_IDLE,
    PHASE_MORNING_DISCHARGE,
    PHASE_OFF,
    STAT_BATTERY_THROUGHPUT_TODAY,
    STAT_BATTERY_WEAR_TODAY_EUR,
    STAT_CHARGED_TODAY,
    STAT_COST_TODAY_EUR,
    STAT_CURTAILMENT_AVOIDED,
    STAT_DISCHARGED_TODAY,
    STAT_FEED_IN_AVOIDED,
    STAT_FEED_IN_INTERVENTIONS,
    STAT_FEED_IN_REVENUE_TODAY_EUR,
    STAT_GRID_DRAW_TODAY,
    STAT_GRID_FEED_IN_TODAY,
    STAT_GRID_TO_BATTERY_TODAY,
    STAT_PV_SAVED,
    STAT_PV_SAVINGS_TODAY_EUR,
    STAT_PV_SELF_CONSUMPTION_TODAY,
    STAT_WALLBOX_ENERGY_TODAY,
)
from .consumption_stats import ConsumptionStats
from .control_engine import (
    MaestroDecision,
    MaestroParams,
    active_tariff_slot as _active_tariff_slot,
    decide,
    forward_looking_charge_target as _forward_looking_charge_target,
    tariff_schedule_from_params as _tariff_schedule_from_params,
)
from .coordinator_act import CoordinatorActMixin
from .coordinator_diagnostics import CoordinatorDiagnosticsMixin
from .coordinator_forecast import CoordinatorForecastMixin
from .coordinator_helpers import (
    E3DC_RSCP_POWER_MODE_MAP,
    POWER_DEBOUNCE_W,
    _build_power_mode_data,
    _effective_discharge_limit_w,
    energy_interval_hours as _energy_interval_hours,
    _ewma_update,
    _limits_changed_vs_sent_values,
    _params_from_options,
    _ramp_bypass_due_to_resync,
    _run_optimizer_sync,
    _tariff_schedule_from_stored,
)
from .coordinator_sensors import CoordinatorSensorsMixin
from .coordinator_sizing import CoordinatorSizingMixin
from .forecast import ForecastResult

# Re-exports for tests and external imports (public API stability).
__all__ = [
    "E3DCMaestroCoordinator",
    "E3DC_RSCP_POWER_MODE_MAP",
    "POWER_DEBOUNCE_W",
    "_build_power_mode_data",
    "_effective_discharge_limit_w",
    "_limits_changed_vs_sent_values",
    "_params_from_options",
    "_ramp_bypass_due_to_resync",
    "_run_optimizer_sync",
    "_tariff_schedule_from_stored",
    "_ewma_update",
]

_LOGGER = logging.getLogger(__name__)


class E3DCMaestroCoordinator(
    CoordinatorActMixin,
    CoordinatorForecastMixin,
    CoordinatorSizingMixin,
    CoordinatorSensorsMixin,
    CoordinatorDiagnosticsMixin,
    DataUpdateCoordinator[dict[str, Any]],
):
    """Central coordinator: poll → decide → act."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        opts = entry.options
        interval = int(opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self._params = _params_from_options(opts)
        # Always use HA's configured location for astro calculations
        self._params.astro_latitude = hass.config.latitude
        self._params.astro_longitude = hass.config.longitude

        # Runtime state
        self.regelung_aktiv: bool = True
        self.force_discharge: bool = False
        self.last_decision: MaestroDecision | None = None
        self.last_phase: str = PHASE_OFF
        self.last_action_info: dict[str, Any] = {}

        # Statistics (reset at midnight, persisted across restarts)
        self.stats: dict[str, float] = {
            STAT_CHARGED_TODAY: 0.0,
            STAT_DISCHARGED_TODAY: 0.0,
            STAT_FEED_IN_INTERVENTIONS: 0,
            STAT_CURTAILMENT_AVOIDED: 0.0,
            STAT_FEED_IN_AVOIDED: 0.0,
            STAT_PV_SAVED: 0.0,
            STAT_GRID_DRAW_TODAY: 0.0,
            STAT_GRID_FEED_IN_TODAY: 0.0,
            STAT_GRID_TO_BATTERY_TODAY: 0.0,
            STAT_BATTERY_THROUGHPUT_TODAY: 0.0,
            STAT_COST_TODAY_EUR: 0.0,
            STAT_FEED_IN_REVENUE_TODAY_EUR: 0.0,
            STAT_PV_SELF_CONSUMPTION_TODAY: 0.0,
            STAT_PV_SAVINGS_TODAY_EUR: 0.0,
            STAT_BATTERY_WEAR_TODAY_EUR: 0.0,
            STAT_WALLBOX_ENERGY_TODAY: 0.0,
        }
        self._last_stats_date: str | None = None
        # Persistence: store stats in HA's .storage so a restart preserves
        # daily counters until the next midnight reset.
        self._stats_store: Store = Store(
            hass, version=1, key=f"{DOMAIN}_stats_{entry.entry_id}"
        )
        self._stats_dirty: bool = False

        # Failsafe / watchdog
        self._consecutive_failures: int = 0
        self._watchdog_notified: bool = False
        # Separate RSCP service-failure counter (sensor reads stay independent)
        self._consecutive_rscp_failures: int = 0
        self._rscp_watchdog_notified: bool = False
        # False after a failed act → force resend next tick even if decision identical
        self._last_rscp_act_ok: bool = True

        # Shutdown / background-task tracking
        self._shutting_down: bool = False
        self._background_tasks: set[asyncio.Task[Any]] = set()
        # Latest pending actuation payload (last-write-wins coalescing).
        self._pending_act: tuple[Any, Any, dict, float | None] | None = None
        self._act_lock: asyncio.Lock = asyncio.Lock()
        self._act_task: asyncio.Task[Any] | None = None

        # Energy integration: actual elapsed time between ticks
        self._last_energy_tick: datetime | None = None

        # Forecast cache (input fingerprint → skip redundant 96-step sims)
        self._forecast_fingerprint: tuple[Any, ...] | None = None
        self._forecast_lock: asyncio.Lock = asyncio.Lock()
        self._forecast_generation: int = 0
        self._forecast_pv_source: str | None = None
        self._auto_run_failed: bool = False

        # Manual charge rate-limit
        self._last_manual_charge: datetime | None = None

        # Heat pump tracking
        self._hp_running: bool = False
        self._hp_last_change: datetime = dt_util.utcnow()

        # Debug log ring buffer (last 50 lines)
        self.debug_log: deque[str] = deque(maxlen=50)
        self.debug_enabled: bool = False

        # Wallbox current tracking for debounce
        self._last_wallbox_current: float | None = None

        # A1: SoC hysteresis – dampened SoC for rule engine
        self._stable_soc: float | None = None

        # A2: Charge-power ramp – last ramped target (internal, not RSCP)
        self._last_applied_charge_power: int = 0
        # Last charge/discharge limits actually sent via e3dc_rscp (for debounce)
        self._last_sent_charge_limit: int | None = None
        self._last_sent_discharge_limit: int | None = None

        # A3: EWMA-geglättete Leistungswerte (anti-flapping)
        self._ewma_pv: float | None = None
        self._ewma_house: float | None = None
        # Wallbox-Leistung separat geglättet (W); 0 wenn kein Sensor konfiguriert
        self._ewma_wallbox: float | None = None

        # Anti-Pendel-Cooldown: Zeitpunkt des letzten Phasenwechsels
        self._last_phase_changed_at: datetime | None = None

        # E3/Phase 1: Curtailment Guard hysteresis state
        self._curtailment_guard_active: bool = False

        # F1+: Forward-Looking – zuletzt errechnetes dynamisches Ziel (für Sensor)
        self._fwd_looking_target: float | None = None

        # Phase D: Verbrauchsadaptive Reserven
        house_sensor = opts.get(CONF_HOUSE_POWER_SENSOR)
        self._consumption_stats: ConsumptionStats | None = (
            ConsumptionStats(hass, house_sensor) if house_sensor else None
        )

        # F1: PV-Profil für Forecast-Simulator
        pv_sensor = opts.get(CONF_PV_POWER_SENSOR)
        self._pv_stats: ConsumptionStats | None = (
            ConsumptionStats(hass, pv_sensor) if pv_sensor else None
        )
        # Last computed forecast (exposed to sensor entities)
        self.forecast: ForecastResult | None = None

        # F3: Auto-Optimierungs-Modus override state
        self._auto_params: MaestroParams | None = None
        self._auto_last_run: datetime | None = None
        self._auto_result = None  # OptimizerResult | None
        # Suppress options-update reload when triggered by entity toggle (not config flow)
        self._skip_reload: bool = False

        # C1: Autonomiezeit – rolling house-power window (~60 min)
        window_size = max(10, int(3600 // max(1, interval)))
        self._house_power_window: deque[float] = deque(maxlen=window_size)

        # Resolved device id for e3dc_rscp service calls
        self._e3dc_device_id: str | None = None

        # PV-Forecast Auto-Detect: cached entity_id after first discovery (avoids
        # repeated full sensor scan and log spam every cycle)
        self._autodetected_pv_sensor: str | None = None
        # Schwacher-PV-Tag: Tagesprognose einmal pro Tag latchen (kein Flip durch
        # Solcast-Updates). Schwelle/Referenz-Params wirken live – siehe
        # ``_is_low_yield_day_active``.
        self._low_yield_latch_date: date | None = None
        self._low_yield_stats_peak_kwh: float | None = None
        self._low_yield_today_kwh: float | None = None

        # Battery & PV Sizing Advisor
        self.sizing_analysis: SizingAnalysisResult | None = None
        self.sizing_running: bool = False
        # Hypothetical scenario sliders (updated by number entities)
        self.sizing_hypothetical_kwh: float = 10.0
        self.sizing_hypothetical_pv_kwp: float = 5.0
        # Live-editable cost inputs (override the static option defaults so the
        # user can replay the cost calculation directly from the dashboard
        # without re-running the full sweep).
        from .const import (
            CONF_SIZING_BATTERY_PRICE_EUR_KWH,
            CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR,
            CONF_SIZING_PV_PRICE_EUR_PER_KWP,
            DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH,
            DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR,
            DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP,
        )
        _opts = entry.options or entry.data or {}
        self.sizing_price_battery_kwh: float = float(
            _opts.get(CONF_SIZING_BATTERY_PRICE_EUR_KWH, DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH)
        )
        self.sizing_price_pv_kwp: float = float(
            _opts.get(CONF_SIZING_PV_PRICE_EUR_PER_KWP, DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP)
        )
        self.sizing_price_inverter: float = float(
            _opts.get(CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR, DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR)
        )
        # Zusatzkosten (Montage, Nebenkosten, …) – nicht in Optionen vorhanden,
        # daher Default 0 €.
        self.sizing_price_extra: float = 0.0
        self._sizing_store: Store = Store(
            hass, version=1, key=f"{DOMAIN}_sizing_{entry.entry_id}"
        )


    async def async_shutdown(self) -> None:
        """Release limits when integration is unloaded."""
        self._shutting_down = True
        for task in list(self._background_tasks):
            task.cancel()
        # Persist stats before shutdown so a restart preserves daily counters
        await self._async_save_stats()
        await self._async_release_limits("Integration entladen")


    @property
    def skip_reload(self) -> bool:
        """True while a live entity write updates options (no full reload)."""
        return self._skip_reload


    def set_regelung_aktiv(self, active: bool) -> None:
        """Called by the master switch entity."""
        was_active = self.regelung_aktiv
        self.regelung_aktiv = active
        if was_active and not active:
            # Transition to OFF: release all limits immediately
            self._create_background_task(
                self._async_release_limits("Master-Switch deaktiviert"),
                "e3dc_maestro_release_limits",
            )
        elif not was_active and active:
            # Transition to ON: reset smoothing state so stale values don't
            # persist from when the rule was off.
            self._ewma_pv = None
            self._ewma_house = None
            self._ewma_wallbox = None
            self._last_phase_changed_at = None
            # Force a fresh decide+act cycle so any new phase
            # (e.g. CURTAILMENT_GUARD) is applied without waiting for the next poll.
            self.last_decision = None
            self._create_background_task(
                self.async_request_refresh(),
                "e3dc_maestro_refresh",
            )


    def set_force_discharge(self, active: bool) -> None:
        """Called by the manual force-discharge switch entity.

        Toggling OFF releases any active discharge limits so the inverter
        returns to normal operation immediately, without waiting for the
        next decide() tick.
        """
        was_active = self.force_discharge
        self.force_discharge = active
        if was_active and not active:
            self._create_background_task(
                self._async_release_limits("Manuelle Entladung deaktiviert"),
                "e3dc_maestro_release_limits",
            )
        # Trigger a refresh so the new state is reflected without delay.
        self._create_background_task(
            self.async_request_refresh(),
            "e3dc_maestro_refresh",
        )


    def update_param(self, key: str, value: Any) -> None:
        """Called by number/select/switch entities when user changes a value."""
        # Lat/lon come from HA config, not user entities
        if key in ("astro_latitude", "astro_longitude"):
            return
        if hasattr(self._params, key):
            setattr(self._params, key, value)
            self._log(f"Parameter '{key}' geändert → {value}")
            # F3: any manual param write invalidates the auto-mode override
            self.invalidate_auto_params()
            self._forecast_fingerprint = None
        # Also persist to options so it survives restarts.
        # Set _skip_reload so the options-update listener doesn't trigger a
        # full integration reload for live entity changes.
        new_options = dict(self.entry.options)
        new_options[key] = value
        self._skip_reload = True
        try:
            self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        finally:
            self._skip_reload = False


    def invalidate_auto_params(self) -> None:
        """Drop the current optimizer override and force a re-run next cycle."""
        if self._auto_params is not None or self._auto_last_run is not None:
            self._auto_params = None
            self._auto_last_run = None
            self._auto_run_failed = False
            self._forecast_fingerprint = None


    @property
    def _active_params(self) -> MaestroParams:
        """Effective MaestroParams: auto override (if active) or manual config."""
        if (
            self._params.auto_mode_enabled
            and self._auto_params is not None
        ):
            return self._auto_params
        return self._params


    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch sensor states and run the rule engine."""
        opts = self.entry.options
        now = dt_util.now()

        # Restore persisted stats on first run after restart (before midnight reset).
        if self._last_stats_date is None:
            await self._async_load_stats()
            await self._async_load_sizing()

        # Reset daily statistics at midnight
        today_str = now.strftime("%Y-%m-%d")
        if self._last_stats_date != today_str:
            self.stats = {k: 0.0 for k in self.stats}
            self._last_stats_date = today_str
            self._watchdog_notified = False
            self._stats_dirty = True

        # Read sensor values
        try:
            state_data = self._read_sensors(opts)
        except ValueError as err:
            self._consecutive_failures += 1
            self._check_watchdog()
            raise UpdateFailed(f"Sensordaten nicht lesbar: {err}") from err

        self._consecutive_failures = 0

        # C1: Append house power to rolling window for autonomy calculation
        self._house_power_window.append(state_data.house_power)

        # A1: SoC hysteresis – only update _stable_soc when change exceeds dead-band
        hysteresis = self._params.soc_hysteresis_percent
        if self._stable_soc is None:
            self._stable_soc = state_data.soc
        elif abs(state_data.soc - self._stable_soc) >= hysteresis:
            self._stable_soc = state_data.soc
        # Feed dampened SoC to rule engine
        state_data = dataclasses.replace(state_data, soc=self._stable_soc)

        # A3: EWMA-Glättung von PV und Hausverbrauch (anti-flapping)
        # grid_power und battery_power bleiben roh – feed_in_limit braucht
        # schnelle Reaktion und wird separat durch Schwellen-Hysterese entstört.
        _instant_pv = state_data.pv_power
        _instant_house = state_data.house_power
        _dt_s = self.update_interval.total_seconds()
        self._ewma_pv = _ewma_update(
            self._ewma_pv, state_data.pv_power or 0.0,
            EWMA_TAU_S, _dt_s, EWMA_JUMP_THRESHOLD_W,
        )
        self._ewma_house = _ewma_update(
            self._ewma_house, state_data.house_power or 0.0,
            EWMA_TAU_S, _dt_s, EWMA_JUMP_THRESHOLD_W,
        )
        self._ewma_wallbox = _ewma_update(
            self._ewma_wallbox, state_data.wallbox_power or 0.0,
            EWMA_TAU_S, _dt_s, EWMA_JUMP_THRESHOLD_W,
        )
        state_data = dataclasses.replace(
            state_data,
            pv_power=self._ewma_pv,
            house_power=self._ewma_house,
            wallbox_power=self._ewma_wallbox or 0.0,
            pv_power_instant=_instant_pv,
            house_power_instant=_instant_house,
        )

        # Current electricity price (optional)
        current_price: float | None = None
        if opts.get(CONF_DYNAMIC_TARIFF_ENABLED) and opts.get(CONF_PRICE_SENSOR):
            current_price = self._read_float(opts[CONF_PRICE_SENSOR])

        # Phase D / F1: refresh rolling consumption stats (≤1×/h).
        # Always run when the sensor is configured – the forecast also needs it,
        # independent of whether adaptive_reserve is enabled.
        if self._consumption_stats is not None:
            try:
                schedule = _tariff_schedule_from_params(self._params)
                ht_slot = _active_tariff_slot(now, schedule)
                # Pick any HT slot of the schedule when none is active right now,
                # so the HT-window mean is still computed during the day.
                if ht_slot is None:
                    for slot in schedule.slots:
                        if slot.class_ == "high":
                            ht_slot = slot
                            break
                await self._consumption_stats.async_refresh(
                    self._params.adaptive_reserve_lookback_days, ht_slot
                )
                if self._params.adaptive_reserve_enabled:
                    state_data = dataclasses.replace(
                        state_data,
                        consumption_avg_w_24h=self._consumption_stats.avg_w_24h,
                        consumption_avg_w_ht_window=self._consumption_stats.avg_w_ht_window,
                        consumption_data_days=self._consumption_stats.data_days,
                    )
            except Exception as err:
                _LOGGER.debug("ConsumptionStats refresh failed: %s", err)

        # F1: Refresh PV stats + compute 24h forecast (≤1×/h)
        if self._pv_stats is not None:
            try:
                await self._pv_stats.async_refresh(
                    self._params.adaptive_reserve_lookback_days, None
                )
            except Exception as err:
                _LOGGER.debug("PV stats refresh failed: %s", err)
        await self._async_update_forecast(state_data, now)
        await self._async_maybe_run_optimizer(state_data, now)

        # Rule engine
        hp_running = self._hp_running
        hp_last_change_min = (dt_util.utcnow() - self._hp_last_change).total_seconds() / 60

        # E3/Phase 1: Curtailment Guard hysteresis update
        if self._params.curtailment_guard_enabled:
            from .control_engine import _curtailment_floor_w
            floor_w = _curtailment_floor_w(state_data, self._params)
            activation_w = float(self.entry.options.get(
                CONF_CURTAILMENT_ACTIVATION_W, DEFAULT_CURTAILMENT_ACTIVATION_W
            ))
            release_w = float(self.entry.options.get(
                CONF_CURTAILMENT_RELEASE_W, DEFAULT_CURTAILMENT_RELEASE_W
            ))
            if not self._curtailment_guard_active and floor_w >= activation_w:
                self._curtailment_guard_active = True
                self._log(f"Curtailment Guard aktiviert (Floor {floor_w:.0f}W ≥ {activation_w:.0f}W)")
            elif self._curtailment_guard_active and floor_w < release_w:
                self._curtailment_guard_active = False
                self._log(f"Curtailment Guard deaktiviert (Floor {floor_w:.0f}W < {release_w:.0f}W)")

        active = self._active_params
        # F1+: Forward-Looking – Ladeziel dynamisch anheben wenn morgen wenig
        # PV erwartet wird. Pure Funktion → kein Persist, nur Tick-Override.
        if active.forward_looking_enabled:
            new_target = _forward_looking_charge_target(
                state_data, active, active.charge_target
            )
            if new_target != active.charge_target:
                active = dataclasses.replace(active, charge_target=new_target)
                self._fwd_looking_target = new_target
            else:
                self._fwd_looking_target = active.charge_target
        else:
            self._fwd_looking_target = None
        decision = decide(
            state_data,
            active,
            now,
            regelung_aktiv=self.regelung_aktiv,
            curtailment_guard_active=self._curtailment_guard_active,
            current_price=current_price,
            hp_running=hp_running,
            hp_last_change_minutes=hp_last_change_min,
            force_discharge=self.force_discharge,
            previous_phase=self.last_phase,
            previous_phase_since=self._last_phase_changed_at,
        )

        # Act on decision (debounced)
        # A2: Charge-power ramp – limit how fast charge power rises
        bypass_ramp = decision.phase in (
            PHASE_OFF, PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT, PHASE_CURTAILMENT_GUARD,
            PHASE_MORNING_DISCHARGE, PHASE_FORCE_DISCHARGE,
        ) or self.low_yield_day_active
        if decision.charge_power_limit is not None:
            target_p = int(decision.charge_power_limit)
            ramp = active.charge_ramp_w_per_cycle
            # Resync-Bypass: zuletzt gesendetes Cap liegt deutlich daneben
            # (Phasenwechsel, Korridor-Dip → Spreading-Rate). Ohne Bypass
            # ramped die Hardware aus 51 W in 200-W-Schritten hoch und
            # verliert mehrere Minuten Lade-Energie.
            if _ramp_bypass_due_to_resync(target_p, self._last_sent_charge_limit, ramp):
                bypass_ramp = True
            if not bypass_ramp and target_p > self._last_applied_charge_power + ramp:
                ramped_p = self._last_applied_charge_power + ramp
                decision = dataclasses.replace(
                    decision,
                    charge_power_limit=float(ramped_p),
                    target_charge_power=float(ramped_p),
                    reason=decision.reason + f" (Anlauf {ramped_p}/{target_p}W)",
                )
                self._last_applied_charge_power = ramped_p
            else:
                self._last_applied_charge_power = target_p
        else:
            self._last_applied_charge_power = 0

        # F0: Gentle-Charge – scale charge power for comfort phases
        _GENTLE_SKIP = {
            PHASE_OFF, PHASE_EMERGENCY, PHASE_FEED_IN_LIMIT,
            PHASE_CURTAILMENT_GUARD, PHASE_MORNING_DISCHARGE, PHASE_FORCE_DISCHARGE,
        }
        if (
            active.gentle_charge_enabled
            and decision.phase not in _GENTLE_SKIP
            and decision.charge_power_limit is not None
        ):
            decision = dataclasses.replace(
                decision,
                charge_power_limit=decision.charge_power_limit * active.gentle_charge_factor,
                reason=decision.reason + f" (Schonladung ×{active.gentle_charge_factor:.0%})",
            )

        await self._async_schedule_act(decision, state_data, opts, current_price)

        previous_phase = self.last_phase
        if decision.phase != previous_phase:
            self._last_phase_changed_at = now
        self.last_decision = decision
        self.last_phase = decision.phase

        # Update statistics
        charged_native = None
        discharged_native = None
        if opts.get(CONF_BATTERY_CHARGED_TODAY_SENSOR):
            charged_native = self._read_float(
                opts[CONF_BATTERY_CHARGED_TODAY_SENSOR], required=False
            )
        if opts.get(CONF_BATTERY_DISCHARGED_TODAY_SENSOR):
            discharged_native = self._read_float(
                opts[CONF_BATTERY_DISCHARGED_TODAY_SENSOR], required=False
            )

        now_utc = dt_util.utcnow()
        interval_h = _energy_interval_hours(
            self._last_energy_tick, now_utc, self.update_interval
        )
        self._last_energy_tick = now_utc

        if charged_native is not None:
            self.stats[STAT_CHARGED_TODAY] = charged_native
        elif interval_h is not None and state_data.battery_power > 0:
            self.stats[STAT_CHARGED_TODAY] += state_data.battery_power / 1000 * interval_h

        if discharged_native is not None:
            self.stats[STAT_DISCHARGED_TODAY] = discharged_native
        elif interval_h is not None and state_data.battery_power < 0:
            self.stats[STAT_DISCHARGED_TODAY] += abs(state_data.battery_power) / 1000 * interval_h

        # v0.2.0 / v0.3.0: Grid energy bookkeeping for cost sensors + sanity check.
        # grid_power: positiv = Einspeisung (über HA-Konvention im Setup), negativ = Bezug.
        # Current buy price: use price_sensor if dynamic, else fixed_buy_price.
        _buy_price = getattr(self._params, "fixed_buy_price", 0.30)
        if opts.get(CONF_DYNAMIC_TARIFF_ENABLED) and current_price is not None:
            _buy_price = current_price
        _feed_in_price = getattr(self._params, "feed_in_price", 0.08)

        if interval_h is not None:
            if state_data.grid_power > 0:
                feed_kwh = state_data.grid_power / 1000 * interval_h
                self.stats[STAT_GRID_FEED_IN_TODAY] += feed_kwh
                self.stats[STAT_FEED_IN_REVENUE_TODAY_EUR] += feed_kwh * _feed_in_price
            elif state_data.grid_power < 0:
                grid_draw_w = abs(state_data.grid_power)
                draw_kwh = grid_draw_w / 1000 * interval_h
                self.stats[STAT_GRID_DRAW_TODAY] += draw_kwh
                self.stats[STAT_COST_TODAY_EUR] += draw_kwh * _buy_price
                # Grid → Akku: Netzbezug UND Akku lädt gleichzeitig.
                if state_data.battery_power > 0:
                    gtb_w = min(grid_draw_w, state_data.battery_power)
                    self.stats[STAT_GRID_TO_BATTERY_TODAY] += gtb_w / 1000 * interval_h

            # Throughput = |Akku-Leistung| für Wear-Cost-Berechnung.
            throughput_kwh = abs(state_data.battery_power) / 1000 * interval_h
            self.stats[STAT_BATTERY_THROUGHPUT_TODAY] += throughput_kwh
            # Wallbox-Energie heute (kWh) – getrennter Verbrauchszähler
            if state_data.wallbox_power > 0:
                self.stats[STAT_WALLBOX_ENERGY_TODAY] += (
                    state_data.wallbox_power / 1000 * interval_h
                )
            # Wear cost: capex / (cycles × 2 × capacity_kwh) × throughput
            _cap = max(getattr(self._params, "battery_capacity_kwh", 10.0), 1.0)
            _cycles = max(getattr(self._params, "battery_total_cycles", 5000.0), 100.0)
            _capex = max(getattr(self._params, "battery_capex_eur", 8000.0), 0.0)
            _wear_per_kwh = _capex / (_cycles * 2.0 * _cap)
            self.stats[STAT_BATTERY_WEAR_TODAY_EUR] += throughput_kwh * _wear_per_kwh

            # PV self-consumption = min(pv, house) per interval (nur direkter PV→Haus-Anteil)
            pv_self_w = min(state_data.pv_power, state_data.house_power)
            if pv_self_w > 0:
                pv_self_kwh = pv_self_w / 1000 * interval_h
                self.stats[STAT_PV_SELF_CONSUMPTION_TODAY] += pv_self_kwh

            # Ersparnis = vermiedener Netzbezug durch Eigenversorgung (PV + Akku-Entladung).
            grid_draw_w_for_savings = max(0.0, -state_data.grid_power)
            self_supplied_w = max(0.0, state_data.house_power - grid_draw_w_for_savings)
            if self_supplied_w > 0:
                self_supplied_kwh = self_supplied_w / 1000 * interval_h
                self.stats[STAT_PV_SAVINGS_TODAY_EUR] += self_supplied_kwh * _buy_price

            # E3/Phase 1: Track avoided curtailment energy
            if decision.phase == PHASE_CURTAILMENT_GUARD and decision.charge_power_limit is not None:
                kwh = decision.charge_power_limit / 1000 * interval_h
                self.stats[STAT_CURTAILMENT_AVOIDED] += kwh
                self.stats[STAT_PV_SAVED] += kwh
            elif (
                decision.phase == PHASE_IDLE
                and self._curtailment_guard_active
                and state_data.battery_power > 0
            ):
                # Abregelschutz war aktiv, aber Akku war voll → E3DC lädt via PV-Überschuss.
                kwh = state_data.battery_power / 1000 * interval_h
                self.stats[STAT_CURTAILMENT_AVOIDED] += kwh
                self.stats[STAT_PV_SAVED] += kwh

            # Feed-in avoided energy while in FEED_IN_LIMIT (time-integrated)
            if decision.phase == PHASE_FEED_IN_LIMIT and decision.feed_in_excess_w is not None:
                kwh = decision.feed_in_excess_w / 1000 * interval_h
                self.stats[STAT_FEED_IN_AVOIDED] += kwh
                self.stats[STAT_PV_SAVED] += kwh

        # Count feed-in interventions once per phase entry, not every poll.
        if decision.phase == PHASE_FEED_IN_LIMIT and previous_phase != PHASE_FEED_IN_LIMIT:
            self.stats[STAT_FEED_IN_INTERVENTIONS] += 1

        # Persist stats roughly once per minute so a restart preserves
        # daily counters. Throttled via _last_stats_save to avoid disk thrash.
        self._stats_dirty = True
        last_save = getattr(self, "_last_stats_save", None)
        if last_save is None or (now - last_save).total_seconds() >= 60:
            self._last_stats_save = now
            await self._async_save_stats()

        return {
            "decision": decision,
            "state": state_data,
            "stats": dict(self.stats),
            "current_price": current_price,
        }


    async def _async_load_stats(self) -> None:
        """Load persisted stats from disk (called once during first refresh)."""
        try:
            data = await self._stats_store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Stats konnten nicht geladen werden: %s", err)
            return
        if not data:
            return
        stored_date = data.get("date")
        today_str = dt_util.now().strftime("%Y-%m-%d")
        if stored_date != today_str:
            # Stale data from a previous day → ignore so the midnight reset
            # path stays authoritative
            return
        stored_stats = data.get("stats")
        if isinstance(stored_stats, dict):
            for key in self.stats:
                if key in stored_stats:
                    self.stats[key] = stored_stats[key]
            self._last_stats_date = stored_date


    async def _async_save_stats(self) -> None:
        """Persist current stats to disk."""
        try:
            await self._stats_store.async_save(
                {
                    "date": self._last_stats_date,
                    "stats": dict(self.stats),
                }
            )
            self._stats_dirty = False
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Stats konnten nicht gesichert werden: %s", err)


    def _log(self, msg: str) -> None:
        ts = dt_util.now().strftime("%H:%M:%S")
        line = f"{ts} {msg}"
        _LOGGER.debug(line)
        if self.debug_enabled:
            self.debug_log.append(line)
