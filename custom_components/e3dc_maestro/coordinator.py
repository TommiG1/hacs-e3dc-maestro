"""DataUpdateCoordinator for E3DC Maestro.

Polls configured sensor entities, runs the rule engine, and calls
e3dc_rscp services when the decision changes (debounced).
Handles Watchdog / Failsafe / Master-Switch off transitions.
"""
from __future__ import annotations

import asyncio
import logging
import math
import statistics
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ADDITIONAL_GENERATION_SENSOR,
    CONF_BATTERY_CHARGED_TODAY_SENSOR,
    CONF_BATTERY_DISCHARGED_TODAY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CURTAILMENT_ACTIVATION_W,
    CONF_CURTAILMENT_GUARD_ENABLED,
    CONF_CURTAILMENT_RELEASE_W,
    CONF_DYNAMIC_TARIFF_ENABLED,
    CONF_EVCC_CHARGING_ENTITY,
    CONF_EVCC_ENABLED,
    CONF_EVCC_MODE_ENTITY,
    CONF_EVCC_NOW_VALUE,
    CONF_GRID_POWER_SENSOR,
    CONF_GRID_POWER_INVERT,
    CONF_HP_ENABLED,
    CONF_HP_MIN_PAUSE_MINUTES,
    CONF_HP_MIN_RUN_MINUTES,
    CONF_HP_SERVICE_OFF,
    CONF_HP_SERVICE_ON,
    CONF_HP_SWITCH_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_PV_FORECAST_ENABLED,
    CONF_PV_FORECAST_SENSOR,
    CONF_PV_FORECAST_SENSOR_DAY2,
    CONF_PV_FORECAST_TODAY_SENSOR,
    CONF_TOMORROW_PV_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_TARIFF_SLOTS,
    CONF_UPDATE_INTERVAL,
    CONF_WALLBOX_ENABLED,
    CONF_WALLBOX_INCLUDED_IN_HOUSE,
    CONF_WALLBOX_MAX_CURRENT,
    CONF_WALLBOX_POWER_SENSOR,
    CONF_WALLBOX_SERVICE_OFF,
    CONF_WALLBOX_SERVICE_ON,
    CONF_WALLBOX_TYPE,
    CONF_WATCHDOG_TIMEOUT,
    DATA_BATTERY_POWER,
    DATA_GRID_POWER,
    DATA_HOUSE_POWER,
    DATA_PV_POWER,
    DATA_SOC,
    DATA_WALLBOX_POWER,
    DEFAULT_CURTAILMENT_ACTIVATION_W,
    DEFAULT_CURTAILMENT_RELEASE_W,
    DEFAULT_UPDATE_INTERVAL,
    EWMA_JUMP_THRESHOLD_W,
    EWMA_TAU_S,
    FEED_IN_PV_DELAY_COOLDOWN_S,
    DEFAULT_WATCHDOG_TIMEOUT,
    DOMAIN,
    E3DC_RSCP_DOMAIN,
    MANUAL_CHARGE_MIN_INTERVAL_HOURS,
    POWER_MODE_CHARGE,
    POWER_MODE_CHARGE_FROM_GRID,
    POWER_MODE_DISCHARGE,
    POWER_MODE_IDLE,
    PHASE_CURTAILMENT_GUARD,
    PHASE_EMERGENCY,
    PHASE_FEED_IN_LIMIT,
    PHASE_FORCE_DISCHARGE,
    PHASE_IDLE,
    PHASE_MORNING_CAP,
    PHASE_MORNING_DISCHARGE,
    PHASE_OFF,
    PHASE_PV_DELAY,
    PHASE_CORRIDOR,
    POWER_MODE_NORMAL,
    SERVICE_CLEAR_POWER_LIMITS,
    SERVICE_MANUAL_CHARGE,
    SERVICE_SET_POWER_LIMITS,
    SERVICE_SET_POWER_MODE,
    SERVICE_SET_WALLBOX_CURRENT,
    STAT_CHARGED_TODAY,
    STAT_CURTAILMENT_AVOIDED,
    STAT_DISCHARGED_TODAY,
    STAT_FEED_IN_AVOIDED,
    STAT_FEED_IN_INTERVENTIONS,
    STAT_PV_SAVED,
    STAT_GRID_DRAW_TODAY,
    STAT_GRID_FEED_IN_TODAY,
    STAT_GRID_TO_BATTERY_TODAY,
    STAT_BATTERY_THROUGHPUT_TODAY,
    STAT_COST_TODAY_EUR,
    STAT_FEED_IN_REVENUE_TODAY_EUR,
    STAT_PV_SELF_CONSUMPTION_TODAY,
    STAT_PV_SAVINGS_TODAY_EUR,
    STAT_BATTERY_WEAR_TODAY_EUR,
    STAT_WALLBOX_ENERGY_TODAY,
    WALLBOX_TYPE_E3DC,
)
from .control_engine import (
    MaestroDecision,
    MaestroParams,
    MaestroState,
    TARIFF_HIGH,
    TARIFF_LOW,
    TARIFF_NORMAL,
    TariffSchedule,
    TariffSlot,
    astro_sunrise_sunset as _astro_sunrise_sunset,
    decide,
    hp_desired_state,
    seasonal_charge_end_hour as _seasonal_charge_end_hour,
    seasonal_reserve_soc as _seasonal_reserve_soc,
    adaptive_emergency_reserve_soc as _adaptive_emergency_reserve_soc,
    adaptive_ht_reserve_soc as _adaptive_ht_reserve_soc,
    active_tariff_slot as _active_tariff_slot,
    tariff_schedule_from_params as _tariff_schedule_from_params,
    forward_looking_charge_target as _forward_looking_charge_target,
    wallbox_desired_current,
)
from .battery_sizing import SizingAnalysisResult, SizingDataLoader, sweep_2d, interpolate_result
from .consumption_stats import ConsumptionStats
from .forecast import ForecastResult, simulate_next_24h
from .optimizer import OptimizerResult, run_optimizer

_LOGGER = logging.getLogger(__name__)


_EWMA_GLITCH_ZERO_FLOOR_W: float = 200.0  # below this, 0-values are not glitches


def _ewma_update(
    prev: float | None,
    new_val: float,
    tau_s: float,
    dt_s: float,
    jump_threshold_w: float,
) -> float:
    """Exponential weighted moving average with jump-reset and zero-glitch guard.

    Falls der neue Wert mehr als *jump_threshold_w* vom Vorgänger abweicht
    (z.B. Wallbox-Start), wird der EWMA sofort auf den neuen Wert gesetzt
    statt träge nachzuführen.

    Zero-Glitch-Guard: Liefert der Sensor exakt 0 W, obwohl der bisherige
    EWMA deutlich über _EWMA_GLITCH_ZERO_FLOOR_W liegt, wird der Wert als
    E3DC-RSCP-Glitch verworfen und der vorherige EWMA-Wert beibehalten.
    """
    if prev is None:
        return new_val
    # Zero-Glitch-Guard: exakter 0-Wert bei laufendem Verbrauch = Sensor-Aussetzer
    if new_val == 0.0 and prev > _EWMA_GLITCH_ZERO_FLOOR_W:
        return prev
    if abs(new_val - prev) > jump_threshold_w:
        return new_val
    alpha = 1.0 - math.exp(-dt_s / max(tau_s, 1e-6))
    return prev + alpha * (new_val - prev)


# How much a power limit must change to trigger a new service call (W)
POWER_DEBOUNCE_W = 50

E3DC_RSCP_POWER_MODE_MAP = {
    POWER_MODE_NORMAL: "0",
    POWER_MODE_IDLE: "1",
    POWER_MODE_DISCHARGE: "2",
    POWER_MODE_CHARGE: "3",
    POWER_MODE_CHARGE_FROM_GRID: "4",
}


def _params_from_options(options: dict[str, Any]) -> MaestroParams:
    """Build MaestroParams from config entry options."""
    p = MaestroParams()
    for attr in p.__dataclass_fields__:
        if attr in options:
            setattr(p, attr, options[attr])
    # Phase C: convert stored slot list (if any) into a TariffSchedule that
    # overrides the legacy ht_*/cheap_threshold conversion.
    schedule = _tariff_schedule_from_stored(options)
    if schedule is not None:
        p.tariff_schedule = schedule
    return p


_VALID_CLASSES = {TARIFF_HIGH, TARIFF_LOW, TARIFF_NORMAL}


def _tariff_schedule_from_stored(options: dict[str, Any]) -> TariffSchedule | None:
    """Parse ``options[CONF_TARIFF_SLOTS]`` into a :class:`TariffSchedule`.

    Returns ``None`` when no slot list is stored, so the legacy ``ht_*`` /
    cheap-threshold fallback in :func:`tariff_schedule_from_params` keeps
    working for unmigrated entries.
    """
    raw = options.get(CONF_TARIFF_SLOTS)
    if not raw:
        return None
    slots: list[TariffSlot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            weekdays = frozenset(int(d) for d in item.get("weekdays", []))
            start_h = float(item["start_h"])
            end_h = float(item["end_h"])
        except (KeyError, TypeError, ValueError):
            continue
        cls = item.get("class_") or item.get("class") or TARIFF_HIGH
        if cls not in _VALID_CLASSES:
            cls = TARIFF_HIGH
        reserve = item.get("min_reserve_soc")
        try:
            reserve_f = float(reserve) if reserve is not None else None
        except (TypeError, ValueError):
            reserve_f = None
        slots.append(
            TariffSlot(
                weekdays=weekdays,
                start_h=start_h,
                end_h=end_h,
                class_=cls,
                min_reserve_soc=reserve_f,
            )
        )
    if not slots:
        return None
    threshold = (
        float(options["cheap_threshold"])
        if options.get(CONF_DYNAMIC_TARIFF_ENABLED)
        and options.get("cheap_threshold") is not None
        else None
    )
    return TariffSchedule(slots=slots, cheap_threshold=threshold)


class E3DCMaestroCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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

        # A2: Charge-power ramp – last value sent to inverter
        self._last_applied_charge_power: int = 0

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
        self._auto_result: "OptimizerResult | None" = None  # forward ref via TYPE_CHECKING
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
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Public helpers used by entities
    # ──────────────────────────────────────────────────────────────────────────

    def set_regelung_aktiv(self, active: bool) -> None:
        """Called by the master switch entity."""
        was_active = self.regelung_aktiv
        self.regelung_aktiv = active
        if was_active and not active:
            # Transition to OFF: release all limits immediately
            self.hass.async_create_task(self._async_release_limits("Master-Switch deaktiviert"))
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
            self.hass.async_create_task(self.async_request_refresh())

    def set_force_discharge(self, active: bool) -> None:
        """Called by the manual force-discharge switch entity.

        Toggling OFF releases any active discharge limits so the inverter
        returns to normal operation immediately, without waiting for the
        next decide() tick.
        """
        was_active = self.force_discharge
        self.force_discharge = active
        if was_active and not active:
            self.hass.async_create_task(
                self._async_release_limits("Manuelle Entladung deaktiviert")
            )
        # Trigger a refresh so the new state is reflected without delay.
        self.hass.async_create_task(self.async_request_refresh())

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

    # ──────────────────────────────────────────────────────────────────────────
    # F3: Auto-Optimierungs-Modus helpers
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def _active_params(self) -> MaestroParams:
        """Effective MaestroParams: auto override (if active) or manual config."""
        if (
            self._params.auto_mode_enabled
            and self._auto_params is not None
        ):
            return self._auto_params
        return self._params

    def invalidate_auto_params(self) -> None:
        """Drop the current optimizer override and force a re-run next cycle."""
        if self._auto_params is not None or self._auto_last_run is not None:
            self._auto_params = None
            self._auto_last_run = None

    # ──────────────────────────────────────────────────────────────────────────
    # Coordinator lifecycle
    # ──────────────────────────────────────────────────────────────────────────

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
        import dataclasses as _dc
        state_data = _dc.replace(state_data, soc=self._stable_soc)

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
        state_data = _dc.replace(
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
                    state_data = _dc.replace(
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
                active = _dc.replace(active, charge_target=new_target)
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
            if not bypass_ramp and target_p > self._last_applied_charge_power + ramp:
                ramped_p = self._last_applied_charge_power + ramp
                import dataclasses as _dc2
                decision = _dc2.replace(
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
            import dataclasses as _dc3
            decision = _dc3.replace(
                decision,
                charge_power_limit=decision.charge_power_limit * active.gentle_charge_factor,
                reason=decision.reason + f" (Schonladung ×{active.gentle_charge_factor:.0%})",
            )

        await self._async_act(decision, state_data, opts, current_price)

        if decision.phase != self.last_phase:
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

        if charged_native is not None:
            self.stats[STAT_CHARGED_TODAY] = charged_native
        elif state_data.battery_power > 0:
            interval_h = self.update_interval.total_seconds() / 3600
            self.stats[STAT_CHARGED_TODAY] += state_data.battery_power / 1000 * interval_h

        if discharged_native is not None:
            self.stats[STAT_DISCHARGED_TODAY] = discharged_native
        elif state_data.battery_power < 0:
            interval_h = self.update_interval.total_seconds() / 3600
            self.stats[STAT_DISCHARGED_TODAY] += abs(state_data.battery_power) / 1000 * interval_h

        # v0.2.0 / v0.3.0: Grid energy bookkeeping for cost sensors + sanity check.
        # grid_power: positiv = Einspeisung (über HA-Konvention im Setup), negativ = Bezug.
        interval_h_g = self.update_interval.total_seconds() / 3600

        # Current buy price: use price_sensor if dynamic, else fixed_buy_price.
        _buy_price = getattr(self._params, "fixed_buy_price", 0.30)
        if opts.get(CONF_DYNAMIC_TARIFF_ENABLED) and current_price is not None:
            _buy_price = current_price
        _feed_in_price = getattr(self._params, "feed_in_price", 0.08)

        if state_data.grid_power > 0:
            feed_kwh = state_data.grid_power / 1000 * interval_h_g
            self.stats[STAT_GRID_FEED_IN_TODAY] += feed_kwh
            self.stats[STAT_FEED_IN_REVENUE_TODAY_EUR] += feed_kwh * _feed_in_price
        elif state_data.grid_power < 0:
            grid_draw_w = abs(state_data.grid_power)
            draw_kwh = grid_draw_w / 1000 * interval_h_g
            self.stats[STAT_GRID_DRAW_TODAY] += draw_kwh
            self.stats[STAT_COST_TODAY_EUR] += draw_kwh * _buy_price
            # Grid → Akku: Netzbezug UND Akku lädt gleichzeitig.
            if state_data.battery_power > 0:
                gtb_w = min(grid_draw_w, state_data.battery_power)
                self.stats[STAT_GRID_TO_BATTERY_TODAY] += gtb_w / 1000 * interval_h_g

        # Throughput = |Akku-Leistung| für Wear-Cost-Berechnung.
        throughput_kwh = abs(state_data.battery_power) / 1000 * interval_h_g
        self.stats[STAT_BATTERY_THROUGHPUT_TODAY] += throughput_kwh
        # Wallbox-Energie heute (kWh) – getrennter Verbrauchszähler
        if state_data.wallbox_power > 0:
            self.stats[STAT_WALLBOX_ENERGY_TODAY] += (
                state_data.wallbox_power / 1000 * interval_h_g
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
            pv_self_kwh = pv_self_w / 1000 * interval_h_g
            self.stats[STAT_PV_SELF_CONSUMPTION_TODAY] += pv_self_kwh

        # Ersparnis = vermiedener Netzbezug durch Eigenversorgung (PV + Akku-Entladung).
        # Logik: Alles, was der Hausverbrauch nicht aus dem Netz bezogen hat, hätte sonst
        # Geld gekostet → das ist die echte Ersparnis. Deckt sowohl PV→Haus als auch
        # Akku→Haus (z. B. nachts) ab.
        grid_draw_w_for_savings = max(0.0, -state_data.grid_power)
        self_supplied_w = max(0.0, state_data.house_power - grid_draw_w_for_savings)
        if self_supplied_w > 0:
            self_supplied_kwh = self_supplied_w / 1000 * interval_h_g
            self.stats[STAT_PV_SAVINGS_TODAY_EUR] += self_supplied_kwh * _buy_price

        # E3/Phase 1: Track avoided curtailment energy
        if decision.phase == PHASE_CURTAILMENT_GUARD and decision.charge_power_limit is not None:
            interval_h = self.update_interval.total_seconds() / 3600
            kwh = decision.charge_power_limit / 1000 * interval_h
            self.stats[STAT_CURTAILMENT_AVOIDED] += kwh
            self.stats[STAT_PV_SAVED] += kwh
        elif (
            decision.phase == PHASE_IDLE
            and self._curtailment_guard_active
            and state_data.battery_power > 0
        ):
            # Abregelschutz war aktiv, aber Akku war voll (SoC ≥ BATTERY_FULL_SOC_CEILING)
            # → Maestro hat idle übergeben, E3DC lädt trotzdem via PV-Überschuss.
            # Tatsächlich geladene Leistung zählen (nicht nur angefordertes Limit).
            interval_h = self.update_interval.total_seconds() / 3600
            kwh = state_data.battery_power / 1000 * interval_h
            self.stats[STAT_CURTAILMENT_AVOIDED] += kwh
            self.stats[STAT_PV_SAVED] += kwh

        # E3/Phase 1: Feed-in interventions counter
        if decision.phase == PHASE_FEED_IN_LIMIT:
            self.stats[STAT_FEED_IN_INTERVENTIONS] += 1
            if decision.feed_in_excess_w is not None:
                interval_h = self.update_interval.total_seconds() / 3600
                kwh = decision.feed_in_excess_w / 1000 * interval_h
                self.stats[STAT_FEED_IN_AVOIDED] += kwh
                self.stats[STAT_PV_SAVED] += kwh

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

    async def async_shutdown(self) -> None:
        """Release limits when integration is unloaded."""
        # Persist stats before shutdown so a restart preserves daily counters
        await self._async_save_stats()
        await self._async_release_limits("Integration entladen")

    # ──────────────────────────────────────────────────────────────────────────
    # Battery & PV Sizing Advisor
    # ──────────────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────────────    # C1 + B1: Computed properties used by sensor platform
    # ──────────────────────────────────────────────────────────────────────────────

    # Mindestanzahl Samples bevor die Autonomie-Schätzung freigegeben wird.
    # Verhindert, dass nach einem Restart eine kurze Lastspitze (z. B.
    # 5 kW Backofen-Anlauf in den ersten 30 s) die ganze Schätzung
    # dominiert („window_minutes=2.0 → 4975 W“-Effekt).
    _AUTONOMY_MIN_SAMPLES = 60  # ~10 min bei 10 s-Polling

    @property
    def avg_house_power_w(self) -> float:
        """Typical house power (W) over the rolling measurement window.

        Liefert den **Median** der absoluten Hausverbrauchswerte – das ist
        robust gegen kurze Lastspitzen (Backofen-Anlauf, WP-Verdichter,
        Wasserkocher), die das arithmetische Mittel über ein 60-min-Fenster
        nach oben verzerren.
        """
        if not self._house_power_window:
            return 0.0
        return statistics.median(abs(v) for v in self._house_power_window)

    @property
    def autonomy_hours(self) -> float | None:
        """Estimated battery autonomy in hours based on current SoC and typical house load."""
        if not self.data or "state" not in self.data:
            return None
        state = self.data["state"]
        # Warm-up-Gate: Solange das Fenster zu kurz ist, ist der Median nicht
        # belastbar (eine 30-s-Spitze würde die Schätzung verzerren). Wir
        # zeigen lieber "unbekannt" als einen unsinnigen Wert.
        if len(self._house_power_window) < self._AUTONOMY_MIN_SAMPLES:
            return None
        avg = self.avg_house_power_w
        if avg < 10:
            # Fallback: aktueller Momentanverbrauch (z. B. wenn der Sensor
            # konstant 0 lieferte und das Window voller Nullen ist).
            current = abs(state.house_power)
            if current < 10:
                current = abs(min(state.battery_power, 0.0))
            if current < 10:
                return None
            avg = current
        soc = state.soc
        kwh_remaining = (soc / 100.0) * self._params.battery_capacity_kwh
        hours = kwh_remaining / (avg / 1000.0)
        return round(min(hours, 999.0), 1)

    @property
    def autonomy_str(self) -> str | None:
        """Autonomy time formatted as 'Xh YYmin'."""
        h = self.autonomy_hours
        if h is None:
            return None
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours}h {minutes:02d}min"

    @property
    def seasonal_reserve_soc(self) -> float | None:
        """Currently active seasonal emergency reserve SoC (%) or None if disabled."""
        if not self._params.seasonal_reserve_enabled:
            return None
        return round(_seasonal_reserve_soc(dt_util.now(), self._params), 1)

    @property
    def adaptive_reserve_soc(self) -> float | None:
        """Currently computed adaptive emergency reserve SoC (%) or None.

        Returns ``None`` when adaptive reserves are disabled or there is not
        yet enough recorder history.
        """
        if not self._params.adaptive_reserve_enabled:
            return None
        if not self.data or "state" not in self.data:
            return None
        value = _adaptive_emergency_reserve_soc(self.data["state"], self._params)
        return round(value, 1) if value is not None else None

    @property
    def adaptive_ht_reserve_soc(self) -> float | None:
        """Currently computed adaptive HT reserve SoC (%) or None."""
        if not self._params.adaptive_reserve_enabled:
            return None
        if not self.data or "state" not in self.data:
            return None
        schedule = _tariff_schedule_from_params(self._params)
        slot = _active_tariff_slot(dt_util.now(), schedule)
        if slot is None:
            for s in schedule.slots:
                if s.class_ == "high":
                    slot = s
                    break
        value = _adaptive_ht_reserve_soc(self.data["state"], self._params, slot)
        return round(value, 1) if value is not None else None

    # ── F1+: Forward-Looking diagnostics ─────────────────────────────────────
    @property
    def forward_looking_target_soc(self) -> float | None:
        """Aktuell vom Forward-Looking errechnetes dynamisches Ladeziel (%).

        Liefert None wenn das Feature aus ist oder noch keine Werte berechnet
        wurden.
        """
        if not self._params.forward_looking_enabled:
            return None
        return self._fwd_looking_target

    @property
    def tomorrow_pv_kwh(self) -> float | None:
        """Erwarteter PV-Ertrag morgen (kWh) – aus konfiguriertem Sensor."""
        if not self.data or "state" not in self.data:
            return None
        return self.data["state"].tomorrow_pv_kwh

    @property
    def tomorrow_deficit_kwh(self) -> float | None:
        """Erwarteter Energie-Defizit morgen = max(0, consumption - pv) (kWh)."""
        if not self.data or "state" not in self.data:
            return None
        s = self.data["state"]
        if s.tomorrow_pv_kwh is None or s.tomorrow_consumption_kwh is None:
            return None
        return round(max(0.0, s.tomorrow_consumption_kwh - s.tomorrow_pv_kwh), 2)

    # ──────────────────────────────────────────────────────────────────────
    # Schwacher-PV-Tag (Akku-Priorität)
    # ──────────────────────────────────────────────────────────────────────

    def _is_low_yield_day_active(self) -> bool:
        """Schwacher Tag aus gelatchter Prognose + aktuellen Params (Schwelle live)."""
        if not self._params.low_yield_priority_enabled:
            return False
        if self._low_yield_today_kwh is None or self._low_yield_today_kwh < 0:
            return False
        from .control_engine import MaestroState, is_low_yield_day

        probe = MaestroState(
            soc=0,
            pv_power=0,
            house_power=0,
            grid_power=0,
            battery_power=0,
            pv_forecast_today_kwh=self._low_yield_today_kwh,
            pv_stats_peak_kwh=self._low_yield_stats_peak_kwh,
        )
        return is_low_yield_day(
            probe, self._params, stats_peak_kwh=self._low_yield_stats_peak_kwh
        )

    @property
    def low_yield_day_active(self) -> bool:
        """True wenn gelatchte Tagesprognose unter der aktuellen Schwelle liegt."""
        return self._is_low_yield_day_active()

    @property
    def low_yield_today_kwh(self) -> float | None:
        """Aktuelle Tagesprognose (kWh), wie sie für die Latch-Auswertung genutzt wurde."""
        return self._low_yield_today_kwh

    @property
    def low_yield_reference_kwh(self) -> float | None:
        """Berechnete Referenz (kWh) aus kWp-Baseline, Statistik und Override."""
        from .control_engine import reference_pv_yield_kwh
        ref = reference_pv_yield_kwh(
            self._params, stats_peak_kwh=self._low_yield_stats_peak_kwh
        )
        return round(ref, 2) if ref > 0 else None

    @property
    def low_yield_ratio(self) -> float | None:
        """Verhältnis Tagesprognose / Referenz (0–1+) oder None."""
        ref = self.low_yield_reference_kwh
        if ref is None or ref <= 0 or self._low_yield_today_kwh is None:
            return None
        return round(self._low_yield_today_kwh / ref, 3)

    @property
    def seasonal_charge_end_h(self) -> float:
        """Currently computed seasonal charge-end hour (fractional, local time)."""
        return round(_seasonal_charge_end_hour(dt_util.now(), self._params), 2)

    @property
    def seasonal_charge_end_str(self) -> str:
        """Seasonal charge-end formatted as HH:MM string."""
        h = _seasonal_charge_end_hour(dt_util.now(), self._params)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    @property
    def astro_charge_start_h(self) -> float | None:
        """Heute berechneter Ladestart (Sonnenaufgang + Offset), nur bei Astro-Modus.

        Liefert None wenn der Astro-Modus deaktiviert ist – dann gibt es
        keinen astronomisch berechneten Ladestart, das Gate aus
        ``charge_start_sunrise_offset_h`` ist inaktiv.
        """
        if not self._params.astro_enabled:
            return None
        sunrise_h, _ = _astro_sunrise_sunset(dt_util.now(), self._params)
        return round(sunrise_h + self._params.charge_start_sunrise_offset_h, 2)

    @property
    def astro_charge_start_str(self) -> str | None:
        """Heutiger astronomischer Ladestart als HH:MM, sonst None."""
        h = self.astro_charge_start_h
        if h is None:
            return None
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    @property
    def tomorrow_charge_end_str(self) -> str:
        """Voraussichtliches Ladeende morgen als HH:MM (gleiche Logik wie heute, +1 Tag)."""
        tomorrow = dt_util.now() + timedelta(days=1)
        h = _seasonal_charge_end_hour(tomorrow, self._params)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    @property
    def pv_delay_charge_start_str(self) -> str | None:
        """Voraussichtlicher Ladestart bei aktiver PV-Verzögerung als HH:MM.

        Liefert None, wenn die aktuelle Phase nicht ``pv_delay`` ist oder
        keine Forecast-Trajektorie vorliegt. Andernfalls wird die erste
        Stunde aus ``forecast.trajectory_phases`` zurückgegeben, in der
        Maestro nicht mehr verzögert. Findet sich in den nächsten 24 h
        keine andere Phase, fällt das Ergebnis auf das saisonale Ladeende
        zurück (späteste Reserveladung).
        """
        if self.last_decision is None or self.last_decision.phase != PHASE_PV_DELAY:
            return None
        now = dt_util.now()
        # Default-Fallback: saisonales Ladeende (späteste Reserve-Ladung)
        fallback_h = _seasonal_charge_end_hour(now, self._params)
        target_h: float | None = None
        if self.forecast is not None and self.forecast.trajectory_phases:
            base = now.replace(minute=0, second=0, microsecond=0)
            for i, phase in enumerate(self.forecast.trajectory_phases):
                if phase != PHASE_PV_DELAY:
                    ts = base + timedelta(hours=i + 1)
                    target_h = ts.hour + ts.minute / 60
                    break
        if target_h is None:
            target_h = fallback_h
        hours = int(target_h)
        minutes = round((target_h - hours) * 60)
        if minutes == 60:
            hours = (hours + 1) % 24
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    @property
    def tomorrow_charge_start_str(self) -> str | None:
        """Voraussichtlicher Ladestart morgen als HH:MM (nur bei Astro-Modus), sonst None."""
        if not self._params.astro_enabled:
            return None
        tomorrow = dt_util.now() + timedelta(days=1)
        sunrise_h, _ = _astro_sunrise_sunset(tomorrow, self._params)
        h = round(sunrise_h + self._params.charge_start_sunrise_offset_h, 2)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    # ──────────────────────────────────────────────────────────────────────────────    # Actor calls
    # ──────────────────────────────────────────────────────────────────────────

    async def _async_act(
        self,
        decision: MaestroDecision,
        state: MaestroState,
        opts: dict,
        current_price: float | None,
    ) -> None:
        """Translate decision into e3dc_rscp service calls."""
        prev = self.last_decision

        # Power mode / limits
        mode_changed = prev is None or prev.power_mode != decision.power_mode
        limits_changed = prev is None or (
            (prev.charge_power_limit is None) != (decision.charge_power_limit is None)
            or (prev.discharge_power_limit is None) != (decision.discharge_power_limit is None)
            or abs((prev.charge_power_limit or 0) - (decision.charge_power_limit or 0)) > POWER_DEBOUNCE_W
            or abs((prev.discharge_power_limit or 0) - (decision.discharge_power_limit or 0)) > POWER_DEBOUNCE_W
        )

        if mode_changed or limits_changed:
            if decision.power_mode == POWER_MODE_NORMAL and decision.charge_power_limit is None and decision.discharge_power_limit is None:
                await self._call_e3dc(SERVICE_CLEAR_POWER_LIMITS, {})
                self._log(f"[{decision.phase}] clear_power_limits → {decision.reason}")
            elif decision.power_mode == POWER_MODE_NORMAL and decision.charge_power_limit is None and decision.discharge_power_limit is not None:
                # Nur Entladung begrenzen (z. B. EVCC Now-Modus) – kein Ladebefehl
                _max_discharge_w = max(0, int(decision.discharge_power_limit))
                await self._call_e3dc(
                    SERVICE_SET_POWER_LIMITS,
                    {"max_discharge": _max_discharge_w},
                )
                self._log(
                    f"[{decision.phase}] set_power_limits max_discharge={_max_discharge_w}W → {decision.reason}"
                )
            elif decision.power_mode is not None:
                # E3DC-RSCP erwartet: max_charge >= 0 ; power_value für mode
                # CHARGE strikt > 0. Decision-Werte können durch
                # gentle_charge_factor (×0.35) oder Float-Rundung (z. B.
                # 1 W × 0.35 → 0) auf 0 fallen. Hier hart auf 1 W heben,
                # damit die Service-Schemas nicht den ganzen
                # Update-Zyklus killen (→ Entitäten "unavailable").
                if decision.charge_power_limit is not None:
                    _max_charge_w = max(0, int(decision.charge_power_limit))
                    await self._call_e3dc(
                        SERVICE_SET_POWER_LIMITS,
                        {"max_charge": _max_charge_w},
                    )
                power_mode_data: dict[str, Any] = {"power_mode": decision.power_mode}
                if decision.charge_power_limit is not None:
                    # CHARGE-Mode verlangt > 0 → mind. 1 W.
                    power_mode_data["power_value"] = max(1, int(decision.charge_power_limit))
                elif (
                    decision.power_mode == POWER_MODE_DISCHARGE
                    and decision.discharge_power_limit is not None
                ):
                    power_mode_data["power_value"] = max(1, int(decision.discharge_power_limit))
                await self._call_e3dc(
                    SERVICE_SET_POWER_MODE,
                    power_mode_data,
                )
                _action_w = (
                    decision.charge_power_limit
                    if decision.charge_power_limit is not None
                    else decision.discharge_power_limit
                )
                self._log(
                    f"[{decision.phase}] mode={decision.power_mode} "
                    f"power={_action_w}W → {decision.reason}"
                )
            _now_local = dt_util.now()
            self.last_action_info = {
                "phase": decision.phase,
                "reason": decision.reason,
                "power_mode": decision.power_mode,
                "charge_power_limit": (
                    int(round(decision.charge_power_limit))
                    if decision.charge_power_limit is not None
                    else None
                ),
                "timestamp": _now_local.isoformat(timespec="seconds"),
                "timestamp_display": _now_local.strftime("%d.%m.%Y %H:%M:%S"),
            }

        # Manual charge (dynamic tariff)
        if decision.manual_charge_kwh and self._can_manual_charge():
            await self._call_e3dc(
                SERVICE_MANUAL_CHARGE,
                {"charge_amount": int(decision.manual_charge_kwh * 1000)},
            )
            self._last_manual_charge = dt_util.utcnow()
            self._log(f"manual_charge {decision.manual_charge_kwh:.1f} kWh")

        # Wallbox
        if opts.get(CONF_WALLBOX_ENABLED):
            await self._async_act_wallbox(state, opts)

        # Heat pump
        if opts.get(CONF_HP_ENABLED):
            hp_last_change_min = (dt_util.utcnow() - self._hp_last_change).total_seconds() / 60
            hp_action = hp_desired_state(
                state, self._params, dt_util.now(), current_price,
                self._hp_running, hp_last_change_min,
            )
            if hp_action is not None:
                await self._async_act_hp(hp_action, opts)

    async def _async_act_wallbox(self, state: MaestroState, opts: dict) -> None:
        desired_current, turn_off = wallbox_desired_current(state, self._params, self._last_wallbox_current or 0)

        if turn_off:
            if self._last_wallbox_current != 0:
                if opts.get(CONF_WALLBOX_TYPE) == WALLBOX_TYPE_E3DC:
                    # Set to minimum to effectively stop
                    await self._call_e3dc(SERVICE_SET_WALLBOX_CURRENT, {"current": 0})
                elif opts.get(CONF_WALLBOX_SERVICE_OFF):
                    await self._call_generic_service(opts[CONF_WALLBOX_SERVICE_OFF])
                self._last_wallbox_current = 0
                self._log("Wallbox ausgeschaltet (kein Überschuss)")
        elif desired_current is not None:
            if self._last_wallbox_current is None or abs(desired_current - self._last_wallbox_current) >= 1.0:
                if opts.get(CONF_WALLBOX_TYPE) == WALLBOX_TYPE_E3DC:
                    await self._call_e3dc(SERVICE_SET_WALLBOX_CURRENT, {"current": int(desired_current)})
                elif opts.get(CONF_WALLBOX_SERVICE_ON):
                    await self._call_generic_service(opts[CONF_WALLBOX_SERVICE_ON])
                self._last_wallbox_current = desired_current
                self._log(f"Wallbox {desired_current:.0f}A (Überschuss)")

    async def _async_act_hp(self, turn_on: bool, opts: dict) -> None:
        service_key = CONF_HP_SERVICE_ON if turn_on else CONF_HP_SERVICE_OFF
        service = opts.get(service_key)
        if service:
            await self._call_generic_service(service)
        elif opts.get(CONF_HP_SWITCH_ENTITY):
            domain = "switch"
            entity_id = opts[CONF_HP_SWITCH_ENTITY]
            await self.hass.services.async_call(
                domain,
                "turn_on" if turn_on else "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            )
        self._hp_running = turn_on
        self._hp_last_change = dt_util.utcnow()
        self._log(f"Wärmepumpe {'ein' if turn_on else 'aus'}geschaltet")

    async def _async_release_limits(self, reason: str) -> None:
        """Call clear_power_limits + set_power_mode normal."""
        try:
            await self._call_e3dc(SERVICE_CLEAR_POWER_LIMITS, {})
            await self._call_e3dc(SERVICE_SET_POWER_MODE, {"power_mode": POWER_MODE_NORMAL})
            self._log(f"Limits freigegeben: {reason}")
        except Exception as err:
            _LOGGER.warning("Fehler beim Freigeben der Limits: %s", err)

    async def _async_update_forecast(
        self, state: "MaestroState", now: datetime
    ) -> None:
        """F1: Recompute the 24-hour forecast using current stats (non-blocking)."""
        try:
            cons_h = (
                self._consumption_stats.hourly_profile_w
                if self._consumption_stats is not None
                and any(v > 0 for v in self._consumption_stats.hourly_profile_w)
                else None
            )
            pv_h = (
                self._pv_stats.hourly_profile_w
                if self._pv_stats is not None
                and any(v > 0 for v in self._pv_stats.hourly_profile_w)
                else None
            )
            if cons_h is None and pv_h is None:
                return  # No historical data yet
            self.forecast = simulate_next_24h(
                soc=state.soc,
                consumption_h=cons_h if cons_h is not None else [state.house_power] * 24,
                pv_h=pv_h if pv_h is not None else [state.pv_power] * 24,
                params=self._params,
                now=now,
                battery_capacity_kwh=self._params.battery_capacity_kwh,
                regelung_aktiv=self.regelung_aktiv,
            )
        except Exception as err:
            _LOGGER.debug("Forecast update failed: %s", err)

    async def _async_maybe_run_optimizer(
        self, state: "MaestroState", now: datetime
    ) -> None:
        """F3: Run grid-search optimizer 1×/day when auto-mode is on.

        - Only runs when ``auto_mode_enabled`` is True
        - Only runs when no override exists for the current local date
        - Requires ≥7 days of consumption AND PV history; falls back otherwise
        - Manual entity writes invalidate the override and force a re-run
        """
        if not self._params.auto_mode_enabled:
            # Auto-mode off → make sure no stale override is applied
            if self._auto_params is not None:
                self.invalidate_auto_params()
            return

        # Only re-run when we haven't optimised for today (local date).
        # NOTE: do NOT gate on ``self._auto_params`` – that field is None when
        # baseline turned out optimal (no override needed).  Re-running every
        # update would only re-evaluate the same daily forecast.
        today = now.date()
        if self._auto_last_run is not None and self._auto_last_run.date() == today:
            return

        cs = self._consumption_stats
        pv = self._pv_stats
        if cs is None or pv is None:
            _LOGGER.warning(
                "Auto-Optimizer: cs=%s pv=%s – Sensor-Konfiguration unvollständig",
                cs, pv,
            )
            return  # missing sensor configuration

        cons_h = list(cs.hourly_profile_w)
        pv_h = list(pv.hourly_profile_w)
        if not any(v > 0 for v in cons_h) or not any(v > 0 for v in pv_h):
            _LOGGER.warning(
                "Auto-Optimizer: Profil leer – cons_max=%.0f pv_max=%.0f "
                "(cons_days=%s, pv_days=%s) – warte auf Statistik",
                max(cons_h) if cons_h else 0, max(pv_h) if pv_h else 0,
                cs.data_days, pv.data_days,
            )
            return  # no useful profile yet

        # If a Solcast/Forecast.Solar sensor provides tomorrow's hourly PV
        # profile (as a list/dict attribute), prefer it over the historic mean.
        # Supported attribute shapes:
        #   list[float]  len=24 → direct hourly W values
        #   list[dict]   with 'pv_estimate'/'value' + 'period_start' keys (Solcast)
        pv_h_forecast = self._read_pv_forecast_profile(now, days_ahead=1)
        if pv_h_forecast is not None:
            pv_h = pv_h_forecast
            # Sum is in W per slot — convert to kWh based on resolution
            _slots_per_hour = max(1, len(pv_h_forecast) // 24)
            _kwh_total = sum(pv_h_forecast) / 1000.0 / _slots_per_hour
            _LOGGER.warning(
                "Auto-Optimizer: Tagesprognose genutzt (max=%.0f W, sum=%.1f kWh, Auflösung=%d min)",
                max(pv_h_forecast), _kwh_total, 60 // _slots_per_hour,
            )
        else:
            _LOGGER.warning(
                "Auto-Optimizer: keine Tagesprognose gefunden \u2192 90d-Mittel (max=%.0f W)",
                max(pv_h),
            )

        # Day-2 forecast (overmorrow relative to ``now``): when available,
        # the optimizer extends its horizon to 48 h so a low end-of-day-1 SoC
        # combined with a poor PV day 2 is correctly penalised.
        pv_h_day2 = self._read_pv_forecast_profile(now, days_ahead=2)
        if pv_h_day2 is not None:
            _slots_per_hour_d2 = max(1, len(pv_h_day2) // 24)
            _LOGGER.warning(
                "Auto-Optimizer: Tag-2-Prognose genutzt (sum=%.1f kWh) \u2192 48 h-Horizont",
                sum(pv_h_day2) / 1000.0 / _slots_per_hour_d2,
            )

        try:
            result = await self.hass.async_add_executor_job(
                _run_optimizer_sync,
                self._params,
                state.soc,
                cons_h,
                pv_h,
                self._params.battery_capacity_kwh,
                self.regelung_aktiv,
                self._params.inverter_power,
                self._params.auto_mode_objective,
                now,
                cs.data_days,
                pv.data_days,
                pv_h_day2,
            )
        except Exception as err:
            _LOGGER.warning("Optimizer run failed: %s", err)
            self._auto_params = None
            self._auto_result = None
            self._auto_last_run = now
            return

        self._auto_result = result
        self._auto_last_run = now
        if result.fallback or not result.overrides:
            # No improvement found / fallback → keep manual params active
            self._auto_params = None
            if result.fallback:
                _LOGGER.warning(
                    "Auto-Optimizer Fallback: %s (cons_days=%s, pv_days=%s)",
                    result.fallback_reason, cs.data_days, pv.data_days,
                )
            else:
                fc = result.forecast
                _LOGGER.warning(
                    "Auto-Optimizer: Baseline optimal (Ziel=%s, Score=%.3f, Grid=%d, "
                    "Curtail=%.2f kWh, Feed=%.2f kWh, Draw=%.2f kWh, Autarkie=%.2f)",
                    result.objective, result.best_score, result.grid_size,
                    fc.pv_curtailed_kwh if fc else 0.0,
                    fc.grid_feed_in_kwh if fc else 0.0,
                    fc.grid_draw_kwh if fc else 0.0,
                    fc.self_sufficiency if fc and fc.self_sufficiency is not None else 0.0,
                )
        else:
            self._auto_params = result.best_params
            _LOGGER.warning(
                "Auto-Optimizer aktiv (Ziel=%s): %s → +%.1f%%",
                result.objective, result.overrides, result.estimated_savings_pct,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Service call helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_e3dc(self, service: str, data: dict) -> None:
        """Call an e3dc_rscp service.

        Verschluckt Schema- und Timeout-Fehler bewusst: Wenn der
        e3dc_rscp-Service einen einzelnen Aufruf ablehnt (z. B. weil
        gentle_charge × 1 W auf 0 rundet) oder das RSCP-Gateway hängt,
        soll *nicht* der gesamte Coordinator-Update-Zyklus abbrechen –
        sonst würden alle Maestro-Entitäten kurzzeitig "unavailable".
        Stattdessen loggen und beim nächsten Tick erneut versuchen.
        """
        if service == SERVICE_SET_POWER_MODE and "power_mode" in data:
            power_mode = data["power_mode"]
            data = {
                **data,
                "power_mode": E3DC_RSCP_POWER_MODE_MAP.get(power_mode, power_mode),
            }
        payload = {"device_id": self._resolve_e3dc_device_id(), **data}
        try:
            async with asyncio.timeout(15):
                await self.hass.services.async_call(
                    E3DC_RSCP_DOMAIN, service, payload, blocking=True
                )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "E3DC Maestro: Service %s.%s hat 15 s nicht geantwortet "
                "(payload=%s) – nächster Tick versucht es erneut.",
                E3DC_RSCP_DOMAIN, service, data,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning(
                "E3DC Maestro: Service %s.%s abgelehnt (payload=%s): %s",
                E3DC_RSCP_DOMAIN, service, data, err,
            )

    def _resolve_e3dc_device_id(self) -> str:
        """Resolve the E3DC device id from one of the configured source sensors."""
        if self._e3dc_device_id is not None:
            return self._e3dc_device_id

        entity_registry = er.async_get(self.hass)
        for option_key in (
            CONF_SOC_SENSOR,
            CONF_PV_POWER_SENSOR,
            CONF_HOUSE_POWER_SENSOR,
            CONF_GRID_POWER_SENSOR,
            CONF_BATTERY_POWER_SENSOR,
        ):
            entity_id = self.entry.options.get(option_key)
            if not entity_id:
                continue
            registry_entry = entity_registry.async_get(entity_id)
            if registry_entry and registry_entry.device_id:
                self._e3dc_device_id = registry_entry.device_id
                return registry_entry.device_id

        raise HomeAssistantError(
            "Konnte keine E3DC device_id aus den konfigurierten Sensorsignalen ermitteln"
        )

    async def _call_generic_service(self, action: dict | str) -> None:
        """Call a user-defined action (from ActionSelector)."""
        if isinstance(action, dict):
            domain = action.get("domain", "")
            service = action.get("service", "")
            service_data = action.get("data", {})
            if domain and service:
                await self.hass.services.async_call(domain, service, service_data, blocking=True)
        elif isinstance(action, str) and "." in action:
            domain, service = action.split(".", 1)
            await self.hass.services.async_call(domain, service, {}, blocking=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Sensor reading
    # ──────────────────────────────────────────────────────────────────────────

    def _read_sensors(self, opts: dict) -> MaestroState:
        soc = self._read_float(opts[CONF_SOC_SENSOR], required=True)
        pv = self._read_power_w(opts[CONF_PV_POWER_SENSOR], required=True)
        additional_generation = 0.0
        if opts.get(CONF_ADDITIONAL_GENERATION_SENSOR):
            additional_generation = self._read_power_w(
                opts[CONF_ADDITIONAL_GENERATION_SENSOR], required=False
            ) or 0.0
        house = self._read_power_w(opts[CONF_HOUSE_POWER_SENSOR], required=True)
        # Wallbox-Verbrauch separat (optional). Wenn der Hausverbrauchszähler die
        # Wallbox bereits enthält (typisch openWB am EVU-Zähler), ziehen wir sie
        # ab, damit die Optimierungs-Logik einen "reinen" Hausverbrauch sieht.
        wallbox = 0.0
        wb_sensor = opts.get(CONF_WALLBOX_POWER_SENSOR)
        if wb_sensor:
            wb_val = self._read_power_w(wb_sensor, required=False)
            if wb_val is not None:
                wallbox = max(0.0, wb_val)
                if opts.get(CONF_WALLBOX_INCLUDED_IN_HOUSE, False) and house is not None:
                    house = max(0.0, house - wallbox)
        grid = self._read_power_w(opts[CONF_GRID_POWER_SENSOR], required=True)
        if grid is not None and opts.get(CONF_GRID_POWER_INVERT, False):
            grid = -grid
        batt = self._read_power_w(opts[CONF_BATTERY_POWER_SENSOR], required=True)
        forecast: float | None = None
        if opts.get(CONF_PV_FORECAST_ENABLED) and opts.get(CONF_PV_FORECAST_SENSOR):
            forecast = self._read_float(opts[CONF_PV_FORECAST_SENSOR], required=False)

        # F1+: Forward-Looking inputs (morgen PV + Wochentags-Verbrauch)
        tomorrow_pv: float | None = None
        if self._params.forward_looking_enabled and opts.get(CONF_TOMORROW_PV_SENSOR):
            tomorrow_pv = self._read_float(
                opts[CONF_TOMORROW_PV_SENSOR], required=False
            )
        tomorrow_consumption: float | None = None
        if self._params.forward_looking_enabled and self._consumption_stats is not None:
            tomorrow_local = dt_util.now() + timedelta(days=1)
            tomorrow_consumption = self._consumption_stats.weekday_total_kwh(
                tomorrow_local.weekday()
            )

        # D1: EVCC state
        evcc_charging = False
        evcc_mode: str | None = None
        if opts.get(CONF_EVCC_ENABLED):
            if opts.get(CONF_EVCC_CHARGING_ENTITY):
                cs = self.hass.states.get(opts[CONF_EVCC_CHARGING_ENTITY])
                if cs and cs.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    evcc_charging = cs.state.lower() in ("true", "on", "1", "yes")
            if opts.get(CONF_EVCC_MODE_ENTITY):
                ms = self.hass.states.get(opts[CONF_EVCC_MODE_ENTITY])
                if ms and ms.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    evcc_mode = ms.state

        # Schwacher-PV-Tag: Tagesprognose + historischer Peak einlesen, latchen.
        today_pv_kwh, peak_pv_kwh = self._resolve_low_yield_inputs(opts)

        return MaestroState(
            soc=soc,
            pv_power=pv + additional_generation,
            house_power=house,
            grid_power=grid,
            battery_power=batt,
            pv_forecast_remaining_kwh=forecast,
            wallbox_power=wallbox,
            evcc_charging=evcc_charging,
            evcc_mode=evcc_mode,
            tomorrow_pv_kwh=tomorrow_pv,
            tomorrow_consumption_kwh=tomorrow_consumption,
            pv_forecast_today_kwh=today_pv_kwh,
            pv_stats_peak_kwh=peak_pv_kwh,
        )

    def _resolve_low_yield_inputs(
        self, opts: dict[str, Any]
    ) -> tuple[float | None, float | None]:
        """Lese Tagesprognose + historischen Peak; latch nur die Eingangswerte.

        Rückgabe ``(today_kwh, peak_kwh)`` für die ``MaestroState``-Felder.
        Die Tagesprognose wird einmal pro lokalem Tag festgehalten, damit
        Solcast-Updates den Tag nicht hin- und herschalten. Schwelle und
        Referenz-Parameter werden in ``_is_low_yield_day_active`` live
        ausgewertet.
        """
        if not self._params.low_yield_priority_enabled:
            self._low_yield_latch_date = None
            self._low_yield_stats_peak_kwh = None
            self._low_yield_today_kwh = None
            return (None, None)

        today_kwh: float | None = None
        sensor_id = opts.get(CONF_PV_FORECAST_TODAY_SENSOR)
        if sensor_id:
            today_kwh = self._read_float(sensor_id, required=False)

        peak_kwh: float | None = None
        if self._pv_stats is not None and self._pv_stats.data_days >= 7:
            peak_kwh = self._pv_stats.peak_daily_yield_kwh()

        # Latchen: nur einmal pro lokalem Tag aktualisieren. Vor dem ersten
        # validen Wert (z. B. direkt nach HA-Start ohne Solcast-Update) bleibt
        # der Latch leer und das Feature ist inaktiv.
        local_today = dt_util.now().date()
        if today_kwh is not None and today_kwh >= 0:
            if (
                self._low_yield_latch_date != local_today
                or self._low_yield_today_kwh is None
            ):
                self._low_yield_today_kwh = today_kwh
                self._low_yield_stats_peak_kwh = peak_kwh
                self._low_yield_latch_date = local_today

        return (self._low_yield_today_kwh, self._low_yield_stats_peak_kwh)

    def _read_float(self, entity_id: str, required: bool = False) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""):
            if required:
                raise ValueError(f"Entity '{entity_id}' nicht verfügbar")
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError) as err:
            if required:
                raise ValueError(f"Entity '{entity_id}' hat keinen numerischen Wert: {state.state}") from err
            return None

    # Unit factors → Watt. Lower-cased lookup keys.
    _POWER_UNIT_TO_W: dict[str, float] = {
        "w": 1.0,
        "watt": 1.0,
        "watts": 1.0,
        "kw": 1000.0,
        "kilowatt": 1000.0,
        "mw": 1_000_000.0,
        "megawatt": 1_000_000.0,
    }

    def _read_power_w(self, entity_id: str, required: bool = False) -> float | None:
        """Read a power sensor and normalise the value to Watt.

        Auto-converts based on the entity's ``unit_of_measurement`` attribute
        (W / kW / MW). Falls back to W if the unit is missing or unknown so
        legacy configurations keep working. The detected unit is cached and
        only logged once per entity to avoid log spam.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None, ""):
            if required:
                raise ValueError(f"Entity '{entity_id}' nicht verfügbar")
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError) as err:
            if required:
                raise ValueError(
                    f"Entity '{entity_id}' hat keinen numerischen Wert: {state.state}"
                ) from err
            return None
        unit = (state.attributes.get("unit_of_measurement") or "").strip().lower()
        factor = self._POWER_UNIT_TO_W.get(unit, 1.0)
        cache = self.__dict__.setdefault("_power_unit_cache", {})
        prev = cache.get(entity_id)
        if prev != (unit, factor):
            cache[entity_id] = (unit, factor)
            if unit and unit not in self._POWER_UNIT_TO_W:
                _LOGGER.warning(
                    "Power sensor '%s' has unknown unit '%s' – treating as W",
                    entity_id, unit,
                )
            elif factor != 1.0:
                _LOGGER.info(
                    "Power sensor '%s' liefert %s – wird automatisch in W umgerechnet (×%g)",
                    entity_id, unit, factor,
                )
        return value * factor

    def _read_pv_forecast_profile(
        self, now: "datetime", days_ahead: int = 1
    ) -> list[float] | None:
        """Try to read a 24h PV forecast (W) from a Solcast/Forecast.Solar sensor.

        Returns a list[float] with **either 24 hourly or 48 half-hourly** mean W
        values (UTC). The simulator (forecast.py) auto-detects the resolution
        from the array length; preserving the higher resolution lets the
        optimiser see PV peaks above the feed-in limit that would otherwise be
        averaged out by hourly bucketing (relevant for plants with strict
        feed-in caps like the 70 % rule).

        ``days_ahead`` selects which forecast day to extract (default 1 = the
        day starting at midnight of ``now``). Use 2 for the day after.
        """
        import datetime as _dt

        def _parse_iso(s: str) -> "_dt.datetime | None":
            try:
                return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None

        target_date = (now + _dt.timedelta(days=days_ahead)).date()
        # Profiles are indexed by UTC hour-of-day (matching consumption/pv stats).
        _UTC = _dt.timezone.utc

        def _to_utc_slot(ts: _dt.datetime) -> tuple[_dt.date, int, int]:
            """Return (date, hour, minute) in UTC."""
            if ts.tzinfo is not None:
                ts_utc = ts.astimezone(_UTC)
            else:
                ts_utc = ts.replace(tzinfo=_UTC)
            return ts_utc.date(), ts_utc.hour, ts_utc.minute

        def _try_extract(attrs) -> list[float] | None:
            # Shape 1: list of dicts with period_start + pv_estimate (kW)
            for key in ("detailedHourly", "forecast", "hourly_data", "forecasts"):
                raw = attrs.get(key)
                if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                    # Collect into 48 half-hour buckets to preserve sub-hour peaks.
                    halfhour: list[list[float]] = [[] for _ in range(48)]
                    for item in raw:
                        ts_str = (
                            item.get("period_start")
                            or item.get("time")
                            or item.get("datetime")
                        )
                        if not ts_str:
                            continue
                        ts = _parse_iso(str(ts_str))
                        if ts is None:
                            continue
                        utc_date, utc_hour, utc_minute = _to_utc_slot(ts)
                        if utc_date != target_date:
                            continue
                        val = (
                            item.get("pv_estimate")
                            or item.get("value")
                            or item.get("pv_estimate90")
                            or 0.0
                        )
                        try:
                            val_w = float(val) * 1000.0  # kW → W
                        except (TypeError, ValueError):
                            continue
                        slot = utc_hour * 2 + (1 if utc_minute >= 30 else 0)
                        halfhour[slot].append(val_w)
                    # Did we get genuine sub-hour data? (any hour has both halves filled)
                    has_halfhour = any(
                        halfhour[h * 2] and halfhour[h * 2 + 1]
                        for h in range(24)
                    )
                    if has_halfhour:
                        # Fill empty slots from the matching hour mean (rare gaps).
                        profile_48 = []
                        for h in range(24):
                            a = halfhour[h * 2]
                            b = halfhour[h * 2 + 1]
                            if a and b:
                                profile_48.append(sum(a) / len(a))
                                profile_48.append(sum(b) / len(b))
                            elif a or b:
                                vals = a or b
                                avg = sum(vals) / len(vals)
                                profile_48.append(avg)
                                profile_48.append(avg)
                            else:
                                profile_48.append(0.0)
                                profile_48.append(0.0)
                        if any(v > 0 for v in profile_48):
                            return profile_48
                    # Fallback to hourly resolution if data is hour-only.
                    profile_24 = []
                    for h in range(24):
                        vals = halfhour[h * 2] + halfhour[h * 2 + 1]
                        profile_24.append(sum(vals) / len(vals) if vals else 0.0)
                    if any(v > 0 for v in profile_24):
                        return profile_24
            # Shape 2: plain list len=24
            for key in ("hourly_wh", "watt_hours_period", "watt"):
                raw = attrs.get(key)
                if isinstance(raw, list) and len(raw) == 24:
                    try:
                        return [float(v) for v in raw]
                    except (TypeError, ValueError):
                        pass
            # Shape 3: dict with ISO datetime keys → Wh (hourly buckets)
            raw = attrs.get("watt_hours")
            if isinstance(raw, dict):
                buckets: list[list[float]] = [[] for _ in range(24)]
                for k, v in raw.items():
                    ts = _parse_iso(str(k))
                    if ts is None:
                        continue
                    utc_date, utc_hour, _ = _to_utc_slot(ts)
                    if utc_date != target_date:
                        continue
                    try:
                        buckets[utc_hour].append(float(v))
                    except (TypeError, ValueError):
                        pass
                profile = [sum(b) / len(b) if b else 0.0 for b in buckets]
                if any(v > 0 for v in profile):
                    return profile
            return None

        opts = self.entry.options
        if not opts.get(CONF_PV_FORECAST_ENABLED):
            return None

        # 1. Try configured sensor first
        # For day-2 (days_ahead=2), prefer the dedicated day-2 sensor if configured
        # (e.g. Solcast: prognose_tag_3). Falls back to main forecast sensor.
        if days_ahead >= 2:
            sensor_id = opts.get(CONF_PV_FORECAST_SENSOR_DAY2) or opts.get(CONF_PV_FORECAST_SENSOR)
        else:
            sensor_id = opts.get(CONF_PV_FORECAST_SENSOR)
        if sensor_id:
            state = self.hass.states.get(sensor_id)
            if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                profile = _try_extract(state.attributes)
                if profile is not None:
                    return profile

        # 2. Auto-detect: scan all sensor.* states for one with detailedHourly/forecast/watt_hours
        # Only for days_ahead=1 — for day-2 we require the configured sensor to provide the data
        # explicitly, otherwise integrations like Solcast (which auto-creates prognose_tag_3..7)
        # would silently extend the horizon to 48 h without the user's awareness.
        if days_ahead != 1:
            return None

        # Use cached result from a previous scan to avoid rescanning every cycle.
        if self._autodetected_pv_sensor is not None:
            cached_state = self.hass.states.get(self._autodetected_pv_sensor)
            if cached_state is not None and cached_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                profile = _try_extract(cached_state.attributes)
                if profile is not None:
                    return profile
            # Cached sensor is gone or no longer usable – clear cache and re-scan below.
            _LOGGER.info(
                "Auto-Optimizer: Gecachter PV-Sensor '%s' nicht mehr verfügbar – erneute Suche",
                self._autodetected_pv_sensor,
            )
            self._autodetected_pv_sensor = None

        for state in self.hass.states.async_all("sensor"):
            attrs = state.attributes
            if not any(
                k in attrs
                for k in ("detailedHourly", "forecast", "hourly_data", "watt_hours")
            ):
                continue
            profile = _try_extract(attrs)
            if profile is not None:
                self._autodetected_pv_sensor = state.entity_id
                _LOGGER.info(
                    "Auto-Optimizer: PV-Tagesprognose aus '%s' erkannt – wird für weitere Zyklen gecacht. "
                    "Tipp: Sensor in der Integration konfigurieren, um Auto-Erkennung zu deaktivieren.",
                    state.entity_id,
                )
                return profile

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Watchdog
    # ──────────────────────────────────────────────────────────────────────────

    def _check_watchdog(self) -> None:
        timeout = int(self.entry.options.get(CONF_WATCHDOG_TIMEOUT, DEFAULT_WATCHDOG_TIMEOUT))
        if timeout == 0:
            return
        ticks_needed = max(1, timeout * 60 // int(self.update_interval.total_seconds()))
        if self._consecutive_failures >= ticks_needed and not self._watchdog_notified:
            _LOGGER.error(
                "E3DC Maestro: Watchdog ausgelöst nach %d Fehlversuchen. "
                "Limits werden freigegeben.",
                self._consecutive_failures,
            )
            self.hass.async_create_task(self._async_release_limits("Watchdog ausgelöst"))
            self.hass.components.persistent_notification.async_create(
                f"E3DC Maestro: Verbindungsproblem nach {timeout} min – "
                "Limits wurden zurückgesetzt.",
                title="E3DC Maestro Warnung",
                notification_id="e3dc_maestro_watchdog",
            )
            self._watchdog_notified = True

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _can_manual_charge(self) -> bool:
        if self._last_manual_charge is None:
            return True
        elapsed = (dt_util.utcnow() - self._last_manual_charge).total_seconds() / 3600
        return elapsed >= MANUAL_CHARGE_MIN_INTERVAL_HOURS

    def _log(self, msg: str) -> None:
        ts = dt_util.now().strftime("%H:%M:%S")
        line = f"{ts} {msg}"
        _LOGGER.debug(line)
        if self.debug_enabled:
            self.debug_log.append(line)


# ──────────────────────────────────────────────────────────────────────────────
# F3: Optimizer sync helper (runs in executor thread)
# ──────────────────────────────────────────────────────────────────────────────


def _run_optimizer_sync(
    base_params,
    soc: float,
    cons_h: list,
    pv_h: list,
    battery_capacity_kwh: float,
    regelung_aktiv: bool,
    max_discharge_power: float,
    objective: str,
    now,
    consumption_data_days: int,
    pv_data_days: int,
    pv_h_day2: list[float] | None = None,
):
    """Thread-safe wrapper for run_optimizer (called via async_add_executor_job)."""
    return run_optimizer(
        base_params=base_params,
        soc=soc,
        consumption_h=cons_h,
        pv_h=pv_h,
        battery_capacity_kwh=battery_capacity_kwh,
        regelung_aktiv=regelung_aktiv,
        max_discharge_power=max_discharge_power,
        objective=objective,
        now=now,
        consumption_data_days=consumption_data_days,
        pv_data_days=pv_data_days,
        pv_h_day2=pv_h_day2,
        # Day-2 consumption: reuse the historic 7-day average (cons_h) since
        # we don't have weekday-specific intra-day forecasts yet.
        consumption_h_day2=cons_h if pv_h_day2 is not None else None,
    )

