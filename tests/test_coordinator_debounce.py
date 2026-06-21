"""Tests for RSCP power-limit debounce and power_mode payload."""
from custom_components.e3dc_maestro.const import (
    POWER_MODE_CHARGE,
    POWER_MODE_DISCHARGE,
    POWER_MODE_IDLE,
    POWER_MODE_NORMAL,
)
from custom_components.e3dc_maestro.coordinator import (
    _build_power_mode_data,
    _effective_discharge_limit_w,
    _limits_changed_vs_sent_values,
    _ramp_bypass_due_to_resync,
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
