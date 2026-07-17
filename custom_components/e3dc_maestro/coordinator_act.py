"""RSCP actuation, wallbox/HP control, and watchdogs for E3DC Maestro."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_POWER_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_HP_ENABLED,
    CONF_HP_SERVICE_OFF,
    CONF_HP_SERVICE_ON,
    CONF_HP_SWITCH_ENTITY,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_WALLBOX_ENABLED,
    CONF_WALLBOX_SERVICE_OFF,
    CONF_WALLBOX_SERVICE_ON,
    CONF_WALLBOX_TYPE,
    CONF_WATCHDOG_TIMEOUT,
    DEFAULT_WATCHDOG_TIMEOUT,
    E3DC_RSCP_DOMAIN,
    MANUAL_CHARGE_MIN_INTERVAL_HOURS,
    POWER_MODE_DISCHARGE,
    POWER_MODE_NORMAL,
    SERVICE_CLEAR_POWER_LIMITS,
    SERVICE_MANUAL_CHARGE,
    SERVICE_SET_POWER_LIMITS,
    SERVICE_SET_POWER_MODE,
    SERVICE_SET_WALLBOX_CURRENT,
    WALLBOX_TYPE_E3DC,
)
from .control_engine import MaestroDecision, MaestroState, hp_desired_state, wallbox_desired_current
from .coordinator_helpers import (
    E3DC_RSCP_POWER_MODE_MAP,
    _build_power_mode_data,
    _effective_discharge_limit_w,
    _limits_changed_vs_sent_values,
)

_LOGGER = logging.getLogger(__name__)


class CoordinatorActMixin:
    def _create_background_task(self, coro: Any, name: str) -> None:
        """Schedule a background task that is cancelled on shutdown."""
        if self._shutting_down:
            if hasattr(coro, "close"):
                coro.close()
            return
        task = self.hass.async_create_task(coro, name=name)
        self._background_tasks.add(task)

        def _done(t: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(t)

        task.add_done_callback(_done)


    def _limits_changed_vs_sent(self, decision: MaestroDecision) -> bool:
        """True when decision limits differ enough from last RSCP call to resend."""
        return _limits_changed_vs_sent_values(
            decision.charge_power_limit,
            _effective_discharge_limit_w(decision, self._params.max_charge_power),
            self._last_sent_charge_limit,
            self._last_sent_discharge_limit,
        )


    async def _async_act(
        self,
        decision: MaestroDecision,
        state: MaestroState,
        opts: dict,
        current_price: float | None,
    ) -> None:
        """Translate decision into e3dc_rscp service calls."""
        if self._shutting_down:
            return

        prev = self.last_decision
        needs_retry = not self._last_rscp_act_ok

        # Power mode / limits
        mode_changed = prev is None or prev.power_mode != decision.power_mode or needs_retry
        limits_changed = self._limits_changed_vs_sent(decision) or needs_retry
        act_attempted = False
        act_ok = True

        if mode_changed or limits_changed:
            act_attempted = True
            if decision.power_mode == POWER_MODE_NORMAL and decision.charge_power_limit is None and decision.discharge_power_limit is None:
                ok = await self._call_e3dc(SERVICE_CLEAR_POWER_LIMITS, {})
                act_ok = ok
                if ok:
                    self._last_sent_charge_limit = None
                    self._last_sent_discharge_limit = None
                    self._log(f"[{decision.phase}] clear_power_limits → {decision.reason}")
            elif decision.power_mode == POWER_MODE_NORMAL and decision.charge_power_limit is None and decision.discharge_power_limit is not None:
                # Nur Entladung begrenzen (z. B. EVCC Now-Modus) – kein Ladebefehl
                _max_discharge_w = max(0, int(decision.discharge_power_limit))
                ok = await self._call_e3dc(
                    SERVICE_SET_POWER_LIMITS,
                    {"max_discharge": _max_discharge_w},
                )
                act_ok = ok
                if ok:
                    self._last_sent_discharge_limit = _max_discharge_w
                    self._log(
                        f"[{decision.phase}] set_power_limits max_discharge={_max_discharge_w}W → {decision.reason}"
                    )
            elif decision.power_mode is not None:
                # E3DC-RSCP erwartet: max_charge >= 0 (set_power_limits) und
                # power_mode mit power_value NUR bei CHARGE/DISCHARGE. Im
                # NORMAL-Modus reicht das Lade-Cap aus; ein zusätzliches
                # power_value verwirrt manche Firmwares.
                limits_data: dict[str, Any] = {}
                if decision.charge_power_limit is not None:
                    limits_data["max_charge"] = max(0, int(decision.charge_power_limit))
                _effective_discharge = _effective_discharge_limit_w(
                    decision, self._params.max_charge_power
                )
                if _effective_discharge is not None:
                    limits_data["max_discharge"] = _effective_discharge
                limits_ok = True
                if limits_data:
                    limits_ok = await self._call_e3dc(
                        SERVICE_SET_POWER_LIMITS,
                        limits_data,
                    )
                power_mode_data = _build_power_mode_data(
                    decision.power_mode,
                    decision.charge_power_limit,
                    decision.discharge_power_limit,
                )
                mode_ok = await self._call_e3dc(
                    SERVICE_SET_POWER_MODE,
                    power_mode_data,
                )
                act_ok = limits_ok and mode_ok
                if limits_ok:
                    if "max_charge" in limits_data:
                        self._last_sent_charge_limit = limits_data["max_charge"]
                    if "max_discharge" in limits_data:
                        self._last_sent_discharge_limit = limits_data["max_discharge"]
                    if (
                        decision.power_mode == POWER_MODE_DISCHARGE
                        and decision.discharge_power_limit is not None
                        and mode_ok
                    ):
                        self._last_sent_discharge_limit = int(decision.discharge_power_limit)
                if act_ok:
                    _action_w = (
                        decision.charge_power_limit
                        if decision.charge_power_limit is not None
                        else decision.discharge_power_limit
                    )
                    self._log(
                        f"[{decision.phase}] mode={decision.power_mode} "
                        f"power={_action_w}W → {decision.reason}"
                    )
            if act_ok:
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
                    # Tatsächlich per e3dc_rscp gesendete Caps – Diagnose für
                    # "Soll != Ist auf der E3DC" (z. B. Debounce-Drift).
                    "sent_charge_power_limit": self._last_sent_charge_limit,
                    "sent_discharge_power_limit": self._last_sent_discharge_limit,
                    "timestamp": _now_local.isoformat(timespec="seconds"),
                    "timestamp_display": _now_local.strftime("%d.%m.%Y %H:%M:%S"),
                }

        if act_attempted:
            self._last_rscp_act_ok = act_ok

        # Manual charge (dynamic tariff)
        if decision.manual_charge_kwh and self._can_manual_charge():
            ok = await self._call_e3dc(
                SERVICE_MANUAL_CHARGE,
                {"charge_amount": int(decision.manual_charge_kwh * 1000)},
            )
            if ok:
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
                ok = True
                if opts.get(CONF_WALLBOX_TYPE) == WALLBOX_TYPE_E3DC:
                    # Set to minimum to effectively stop
                    ok = await self._call_e3dc(SERVICE_SET_WALLBOX_CURRENT, {"current": 0})
                elif opts.get(CONF_WALLBOX_SERVICE_OFF):
                    await self._call_generic_service(opts[CONF_WALLBOX_SERVICE_OFF])
                if ok:
                    self._last_wallbox_current = 0
                    self._log("Wallbox ausgeschaltet (kein Überschuss)")
        elif desired_current is not None:
            if self._last_wallbox_current is None or abs(desired_current - self._last_wallbox_current) >= 1.0:
                ok = True
                if opts.get(CONF_WALLBOX_TYPE) == WALLBOX_TYPE_E3DC:
                    ok = await self._call_e3dc(
                        SERVICE_SET_WALLBOX_CURRENT, {"current": int(desired_current)}
                    )
                elif opts.get(CONF_WALLBOX_SERVICE_ON):
                    await self._call_generic_service(opts[CONF_WALLBOX_SERVICE_ON])
                if ok:
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
        if self._shutting_down and reason != "Integration entladen":
            return
        try:
            clear_ok = await self._call_e3dc(SERVICE_CLEAR_POWER_LIMITS, {})
            mode_ok = await self._call_e3dc(
                SERVICE_SET_POWER_MODE, {"power_mode": POWER_MODE_NORMAL}
            )
            if clear_ok and mode_ok:
                self._last_sent_charge_limit = None
                self._last_sent_discharge_limit = None
                self._last_rscp_act_ok = True
                self._log(f"Limits freigegeben: {reason}")
        except Exception as err:
            _LOGGER.warning("Fehler beim Freigeben der Limits: %s", err)


    async def _call_e3dc(self, service: str, data: dict) -> bool:
        """Call an e3dc_rscp service. Return True on success.

        Verschluckt Schema- und Timeout-Fehler bewusst: Wenn der
        e3dc_rscp-Service einen einzelnen Aufruf ablehnt (z. B. weil
        gentle_charge × 1 W auf 0 rundet) oder das RSCP-Gateway hängt,
        soll *nicht* der gesamte Coordinator-Update-Zyklus abbrechen –
        sonst würden alle Maestro-Entitäten kurzzeitig "unavailable".
        Stattdessen loggen und beim nächsten Tick erneut versuchen.
        Caller must only update ``_last_sent_*`` after a True return.
        """
        if service == SERVICE_SET_POWER_MODE and "power_mode" in data:
            power_mode = data["power_mode"]
            data = {
                **data,
                "power_mode": E3DC_RSCP_POWER_MODE_MAP.get(power_mode, power_mode),
            }
        try:
            payload = {"device_id": self._resolve_e3dc_device_id(), **data}
        except HomeAssistantError as err:
            _LOGGER.warning("E3DC Maestro: device_id nicht auflösbar: %s", err)
            self._note_rscp_failure()
            return False
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
            self._note_rscp_failure()
            return False
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning(
                "E3DC Maestro: Service %s.%s abgelehnt (payload=%s): %s",
                E3DC_RSCP_DOMAIN, service, data, err,
            )
            self._note_rscp_failure()
            return False

        self._consecutive_rscp_failures = 0
        if self._rscp_watchdog_notified:
            self._rscp_watchdog_notified = False
        return True


    def _note_rscp_failure(self) -> None:
        """Increment RSCP failure counter and trip watchdog if needed."""
        self._consecutive_rscp_failures += 1
        self._check_rscp_watchdog()


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
            self._create_background_task(
                self._async_release_limits("Watchdog ausgelöst"),
                "e3dc_maestro_watchdog_release",
            )
            self.hass.components.persistent_notification.async_create(
                f"E3DC Maestro: Verbindungsproblem nach {timeout} min – "
                "Limits wurden zurückgesetzt.",
                title="E3DC Maestro Warnung",
                notification_id="e3dc_maestro_watchdog",
            )
            self._watchdog_notified = True


    def _check_rscp_watchdog(self) -> None:
        """Trip when consecutive RSCP service calls fail (independent of sensors)."""
        timeout = int(self.entry.options.get(CONF_WATCHDOG_TIMEOUT, DEFAULT_WATCHDOG_TIMEOUT))
        if timeout == 0:
            return
        ticks_needed = max(1, timeout * 60 // int(self.update_interval.total_seconds()))
        if self._consecutive_rscp_failures >= ticks_needed and not self._rscp_watchdog_notified:
            _LOGGER.error(
                "E3DC Maestro: RSCP-Watchdog ausgelöst nach %d Servicefehlern. "
                "Limits werden freigegeben.",
                self._consecutive_rscp_failures,
            )
            self._create_background_task(
                self._async_release_limits("RSCP-Watchdog ausgelöst"),
                "e3dc_maestro_rscp_watchdog_release",
            )
            self.hass.components.persistent_notification.async_create(
                f"E3DC Maestro: RSCP-Servicefehler nach {timeout} min – "
                "Limits wurden zurückgesetzt.",
                title="E3DC Maestro Warnung",
                notification_id="e3dc_maestro_rscp_watchdog",
            )
            self._rscp_watchdog_notified = True


    def _can_manual_charge(self) -> bool:
        if self._last_manual_charge is None:
            return True
        elapsed = (dt_util.utcnow() - self._last_manual_charge).total_seconds() / 3600
        return elapsed >= MANUAL_CHARGE_MIN_INTERVAL_HOURS
