"""Tests for RSCP power-limit debounce and power_mode payload."""
from collections import deque

from custom_components.e3dc_maestro.const import (
    PHASE_CORRIDOR,
    PHASE_CURTAILMENT_GUARD,
    PHASE_EMERGENCY,
    PHASE_FAST_FLOOR,
    PHASE_IDLE,
    PHASE_SPREADING,
    POWER_MODE_CHARGE,
    POWER_MODE_DISCHARGE,
    POWER_MODE_IDLE,
    POWER_MODE_NORMAL,
)
from custom_components.e3dc_maestro.coordinator import (
    _action_history_changed,
    _build_power_mode_data,
    _effective_discharge_limit_w,
    _limits_changed_vs_sent_values,
    _ramp_bypass_due_to_resync,
    _ramp_bypass_for_phase,
)
from custom_components.e3dc_maestro.control_engine import MaestroDecision


def test_slow_ramp_from_previous_tick_does_not_resend():
    """Consecutive decisions within debounce must not trigger alone."""
    assert _limits_changed_vs_sent_values(59.0, None, 51, None) is False
    assert _limits_changed_vs_sent_values(68.0, None, 59, None) is False


def test_drift_from_last_sent_triggers_resend():
    """Stale E3DC cap must be updated once decision drifts far enough."""
    assert _limits_changed_vs_sent_values(1980.0, None, 51, None) is True
    assert _limits_changed_vs_sent_values(102.0, None, 51, None) is True


def test_none_transition_triggers_resend():
    assert _limits_changed_vs_sent_values(None, None, 51, None) is True
    assert _limits_changed_vs_sent_values(100.0, None, None, None) is True


def test_large_drop_triggers_resend():
    assert _limits_changed_vs_sent_values(51.0, None, 1019, None) is True


# ──────────────────────────────────────────────────────────────────────────────
# set_power_mode payload: power_value nur bei CHARGE/DISCHARGE
# ──────────────────────────────────────────────────────────────────────────────


def test_power_mode_data_normal_omits_power_value():
    """NORMAL-Mode darf kein power_value mitschicken (set_power_limits
    setzt das Lade-Cap; doppelte Felder verwirren manche Firmwares)."""
    data = _build_power_mode_data(POWER_MODE_NORMAL, 2000.0, None)
    assert data == {"power_mode": POWER_MODE_NORMAL}


def test_power_mode_data_idle_omits_power_value():
    """IDLE benötigt kein power_value (kein Lade-/Entlade-Bedarf)."""
    data = _build_power_mode_data(POWER_MODE_IDLE, None, None)
    assert data == {"power_mode": POWER_MODE_IDLE}


def test_power_mode_data_charge_attaches_power_value():
    data = _build_power_mode_data(POWER_MODE_CHARGE, 1980.0, None)
    assert data == {"power_mode": POWER_MODE_CHARGE, "power_value": 1980}


def test_power_mode_data_charge_clamps_zero_to_one_watt():
    """gentle_charge_factor × Rundung kann 0 erzeugen; CHARGE verlangt > 0."""
    data = _build_power_mode_data(POWER_MODE_CHARGE, 0.4, None)
    assert data["power_value"] == 1


def test_power_mode_data_discharge_uses_discharge_limit():
    data = _build_power_mode_data(POWER_MODE_DISCHARGE, None, 800.0)
    assert data == {"power_mode": POWER_MODE_DISCHARGE, "power_value": 800}


# ──────────────────────────────────────────────────────────────────────────────
# Ramp-Bypass bei großer Abweichung zwischen Soll und zuletzt gesendetem Cap
# ──────────────────────────────────────────────────────────────────────────────


def test_ramp_bypass_resync_skipped_without_last_sent():
    """Ohne vorherigen Send (Cold Start) bleibt die Rampe aktiv."""
    assert _ramp_bypass_due_to_resync(2000, None, 200) is False


def test_ramp_bypass_resync_triggers_on_large_gap():
    """Nach Korridor-Dip (51 W gesendet) und Soll 2 kW: Rampe überspringen."""
    assert _ramp_bypass_due_to_resync(2000, 51, 200) is True


def test_ramp_bypass_resync_respects_min_threshold():
    """Kleine Drift (< 500 W) ramped weiterhin sanft."""
    assert _ramp_bypass_due_to_resync(450, 50, 200) is False


def test_ramp_bypass_resync_scales_with_ramp_size():
    """Bei großzügiger Rampe (1000 W/Zyklus) gilt 2 × ramp = 2000 W als Schwelle."""
    assert _ramp_bypass_due_to_resync(1500, 0, 1000) is False
    assert _ramp_bypass_due_to_resync(2500, 0, 1000) is True


# ──────────────────────────────────────────────────────────────────────────────
# Phase 5: Ramp-Bypass hängt an decision.battery_priority, nicht am
# Ganztags-Flag low_yield_day_active.
# ──────────────────────────────────────────────────────────────────────────────


def test_ramp_bypass_active_for_hardcoded_phases_without_battery_priority():
    """Notfall-Phasen lösen den Bypass unabhängig von battery_priority aus."""
    d = MaestroDecision(phase=PHASE_EMERGENCY, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(d) is True

    d2 = MaestroDecision(phase=PHASE_CURTAILMENT_GUARD, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(d2) is True


def test_ramp_bypass_inactive_for_normal_phase_without_battery_priority():
    """Ohne battery_priority und außerhalb der Sonderphasen bleibt die Rampe aktiv."""
    d = MaestroDecision(phase=PHASE_CORRIDOR, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(d) is False

    d2 = MaestroDecision(phase=PHASE_SPREADING, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(d2) is False


def test_ramp_bypass_active_when_battery_priority_set():
    """Abschnitt 6.96 (Schwacher-PV-Tag / Prognose-Gate) hat diesen Tick gegriffen."""
    d = MaestroDecision(phase=PHASE_CORRIDOR, reason="x", battery_priority=True)
    assert _ramp_bypass_for_phase(d) is True


def test_ramp_bypass_not_tied_to_day_flag_only_to_decision():
    """Kernpunkt Phase 5: Sobald battery_priority in der Entscheidung wieder
    False ist (z. B. weil die Bedarfsprüfung freigegeben hat), bleibt die
    Rampe aktiv – unabhängig davon, ob der Tag insgesamt als "schwach"
    markiert war. Der frühere Bug war das Ganztags-Flag, das dies verhinderte."""
    released = MaestroDecision(phase=PHASE_SPREADING, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(released) is False

    still_active = MaestroDecision(phase=PHASE_CORRIDOR, reason="x", battery_priority=True)
    assert _ramp_bypass_for_phase(still_active) is True

    idle = MaestroDecision(phase=PHASE_IDLE, reason="x", battery_priority=False)
    assert _ramp_bypass_for_phase(idle) is False


# ──────────────────────────────────────────────────────────────────────────────
# Effektives Entlade-Limit (implizit frei = WR-Nennleistung)
# ──────────────────────────────────────────────────────────────────────────────


def _decision(**kwargs) -> MaestroDecision:
    return MaestroDecision(phase="corridor", reason="test", **kwargs)


def test_effective_discharge_explicit_cap():
    d = _decision(charge_power_limit=2000.0, discharge_power_limit=800.0)
    assert _effective_discharge_limit_w(d, 9000) == 800


def test_effective_discharge_free_with_active_charge():
    d = _decision(charge_power_limit=2000.0, discharge_power_limit=None)
    assert _effective_discharge_limit_w(d, 9000) == 9000


def test_effective_discharge_none_without_charge():
    d = _decision(charge_power_limit=None, discharge_power_limit=None)
    assert _effective_discharge_limit_w(d, 9000) is None


def test_debounce_uses_effective_discharge_not_none():
    """Nach erstem Send (9000 W Entladung frei) darf None-Soll nicht ständig retriggern."""
    d = _decision(charge_power_limit=2040.0, discharge_power_limit=None)
    eff = _effective_discharge_limit_w(d, 9000)
    assert _limits_changed_vs_sent_values(2048.0, eff, 2040, 9000) is False
    assert _limits_changed_vs_sent_values(2100.0, eff, 2040, 9000) is True


# ──────────────────────────────────────────────────────────────────────────────
# Energy integration / forecast helpers / retry semantics
# ──────────────────────────────────────────────────────────────────────────────


def test_energy_interval_skips_first_tick():
    from datetime import datetime, timedelta, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import energy_interval_hours

    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    assert energy_interval_hours(None, now, timedelta(seconds=30)) is None


def test_energy_interval_uses_elapsed_and_clamps():
    from datetime import datetime, timedelta, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import energy_interval_hours

    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(seconds=30)
    assert abs(energy_interval_hours(last, now, timedelta(seconds=30)) - (30 / 3600)) < 1e-9

    long_gap = now - timedelta(seconds=600)
    # clamp to 3 × 30s = 90s
    assert abs(energy_interval_hours(long_gap, now, timedelta(seconds=30)) - (90 / 3600)) < 1e-9


def test_quarter_slot_floors_to_15_min():
    from datetime import datetime, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import quarter_slot

    now = datetime(2026, 7, 17, 12, 37, 40, tzinfo=timezone.utc)
    assert quarter_slot(now) == datetime(2026, 7, 17, 12, 30, 0, tzinfo=timezone.utc)


def test_forecast_fingerprint_stable_within_quarter():
    from datetime import datetime, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import (
        forecast_input_fingerprint,
        quarter_slot,
    )

    now = datetime(2026, 7, 17, 12, 31, tzinfo=timezone.utc)
    later = datetime(2026, 7, 17, 12, 44, tzinfo=timezone.utc)
    kwargs = dict(
        soc=55.2,
        regelung_aktiv=True,
        cons_h=[300.0] * 24,
        pv_h=[1000.0] * 24,
        params_key=(True, 40.0, 10.0),
    )
    a = forecast_input_fingerprint(quarter=quarter_slot(now), **kwargs)
    b = forecast_input_fingerprint(quarter=quarter_slot(later), **kwargs)
    assert a == b


def test_forecast_fingerprint_changes_on_soc_or_quarter():
    from datetime import datetime, timedelta, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import (
        forecast_input_fingerprint,
        quarter_slot,
    )

    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    base = dict(
        regelung_aktiv=True,
        cons_h=[300.0] * 24,
        pv_h=[1000.0] * 24,
        params_key=(True, 40.0, 10.0),
        quarter=quarter_slot(now),
    )
    a = forecast_input_fingerprint(soc=50.0, **base)
    b = forecast_input_fingerprint(soc=60.0, **base)
    c = forecast_input_fingerprint(
        soc=50.0,
        **{**base, "quarter": quarter_slot(now + timedelta(minutes=15))},
    )
    assert a != b
    assert a != c


def test_forecast_target_date_zero_is_today():
    from datetime import datetime, timezone
    from custom_components.e3dc_maestro.coordinator_helpers import forecast_target_date

    now = datetime(2026, 7, 17, 22, 0, tzinfo=timezone.utc)
    assert forecast_target_date(now, 0) == now.date()
    assert forecast_target_date(now, 1).isoformat() == "2026-07-18"


def test_rscp_retry_forced_when_last_act_failed():
    """Same decision must resend when previous RSCP act failed."""
    last_rscp_act_ok = False
    prev_mode = POWER_MODE_NORMAL
    decision_mode = POWER_MODE_NORMAL
    needs_retry = not last_rscp_act_ok
    mode_changed = prev_mode is None or prev_mode != decision_mode or needs_retry
    limits_changed = _limits_changed_vs_sent_values(100.0, None, 100, None) or needs_retry
    assert mode_changed is True
    assert limits_changed is True


def test_rscp_success_does_not_resend_identical_limits():
    last_rscp_act_ok = True
    needs_retry = not last_rscp_act_ok
    assert (_limits_changed_vs_sent_values(100.0, None, 100, None) or needs_retry) is False


# ──────────────────────────────────────────────────────────────────────────────
# Action-History (News-Ticker): nur bei (phase, reason)-Wechsel anhängen
# ──────────────────────────────────────────────────────────────────────────────


def test_action_history_changed_true_when_empty():
    """Erster Eintrag (Cold Start) wird immer angehängt."""
    assert _action_history_changed(None, PHASE_CORRIDOR, "Korridor aktiv") is True


def test_action_history_changed_false_for_identical_phase_and_reason():
    """Gleicher Tick-Ergebnis (gleiche Phase + gleicher Grund) spammt nicht."""
    last = {"phase": PHASE_CORRIDOR, "reason": "Korridor aktiv"}
    assert _action_history_changed(last, PHASE_CORRIDOR, "Korridor aktiv") is False


def test_action_history_changed_true_on_phase_change():
    last = {"phase": PHASE_CORRIDOR, "reason": "Korridor aktiv"}
    assert _action_history_changed(last, PHASE_FAST_FLOOR, "Korridor aktiv") is True


def test_action_history_changed_true_on_reason_change_same_phase():
    """Gleiche Phase, aber geänderter Grund (z. B. neuer SoC-Wert im Text) zählt
    als Wechsel – der Ticker soll die Begründung aktualisieren."""
    last = {"phase": PHASE_FAST_FLOOR, "reason": "SoC 57 % < Floor 60 %"}
    assert _action_history_changed(last, PHASE_FAST_FLOOR, "SoC 59 % < Floor 60 %") is True


def test_action_history_deque_caps_at_maxlen_eight():
    """Ringpuffer behält nur die letzten 8 Einträge, neueste zuerst (appendleft)."""
    history: deque[dict] = deque(maxlen=8)
    for i in range(12):
        last = history[0] if history else None
        phase = f"phase_{i}"
        reason = f"reason_{i}"
        if _action_history_changed(last, phase, reason):
            history.appendleft({"phase": phase, "reason": reason})

    assert len(history) == 8
    # Neuester Eintrag (phase_11) steht vorne, älteste vier (0-3) sind verdrängt.
    assert history[0]["phase"] == "phase_11"
    assert history[-1]["phase"] == "phase_4"
    assert all(int(e["phase"].split("_")[1]) >= 4 for e in history)


def test_action_history_deque_skips_duplicate_consecutive_entries():
    """Mehrere identische Ticks in Folge erzeugen nur einen History-Eintrag."""
    history: deque[dict] = deque(maxlen=8)
    ticks = [
        (PHASE_CORRIDOR, "Korridor aktiv"),
        (PHASE_CORRIDOR, "Korridor aktiv"),
        (PHASE_CORRIDOR, "Korridor aktiv"),
        (PHASE_FAST_FLOOR, "SoC 57 % < Floor 60 %"),
        (PHASE_FAST_FLOOR, "SoC 57 % < Floor 60 %"),
    ]
    for phase, reason in ticks:
        last = history[0] if history else None
        if _action_history_changed(last, phase, reason):
            history.appendleft({"phase": phase, "reason": reason})

    assert len(history) == 2
    assert history[0]["phase"] == PHASE_FAST_FLOOR
    assert history[1]["phase"] == PHASE_CORRIDOR
