"""Tests for the decision explanation sensor."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.e3dc_maestro.const import ALL_PHASES
from custom_components.e3dc_maestro.control_engine import (
    MaestroDecision,
    MaestroParams,
    MaestroState,
)
from custom_components.e3dc_maestro.explanation import decision_explanation as _decision_explanation


def _make_state(**overrides) -> MaestroState:
    base = dict(
        soc=55.0,
        pv_power=2500.0,
        house_power=600.0,
        grid_power=0.0,
        battery_power=0.0,
        pv_forecast_remaining_kwh=12.5,
        evcc_charging=False,
        evcc_mode=None,
    )
    base.update(overrides)
    return MaestroState(**base)


def _make_coord(decision: MaestroDecision | None, **state_overrides):
    state = _make_state(**state_overrides) if decision is not None else None
    return SimpleNamespace(
        last_decision=decision,
        data={"state": state} if state is not None else None,
        _params=MaestroParams(),
    )


@pytest.mark.parametrize("phase", ALL_PHASES)
def test_explanation_for_every_phase_is_nonempty_german_sentence(phase: str) -> None:
    """All 17 phases must produce a non-empty, properly terminated sentence."""
    decision = MaestroDecision(
        phase=phase,
        reason=f"engine reason for {phase}",
        charge_power_limit=1500.0,
        discharge_power_limit=2000.0,
        target_soc=70.0,
        target_charge_power=1800.0,
        feed_in_excess_w=450.0,
    )
    coord = _make_coord(decision, evcc_mode="now")
    text = _decision_explanation(coord)

    assert text, f"empty explanation for phase {phase}"
    assert isinstance(text, str)
    assert len(text) <= 255
    # Should not be the bare engine fallback for known phases
    assert not text.startswith(f"Phase {phase}:"), (
        f"phase {phase!r} fell into the unknown-phase fallback"
    )


def test_explanation_when_no_decision() -> None:
    coord = SimpleNamespace(last_decision=None, data=None, _params=MaestroParams())
    assert _decision_explanation(coord) == "Noch keine Entscheidung getroffen."


def test_explanation_unknown_phase_uses_engine_reason() -> None:
    decision = MaestroDecision(phase="future_phase_xyz", reason="weil halt")
    coord = _make_coord(decision)
    text = _decision_explanation(coord)
    assert "future_phase_xyz" in text
    assert "weil halt" in text


def test_explanation_tolerates_missing_state() -> None:
    """If coord.data is missing, idle phase must still render without crashing."""
    decision = MaestroDecision(phase="idle", reason="ok")
    coord = SimpleNamespace(last_decision=decision, data=None, _params=MaestroParams())
    text = _decision_explanation(coord)
    assert text
    assert "—" in text  # fallback marker for missing values


def test_explanation_emergency_mentions_threshold() -> None:
    decision = MaestroDecision(
        phase="emergency", reason="x", charge_power_limit=3000.0
    )
    params = MaestroParams()
    params.charge_threshold = 15.0
    coord = SimpleNamespace(
        last_decision=decision,
        data={"state": _make_state(soc=10.0)},
        _params=params,
    )
    text = _decision_explanation(coord)
    assert "10%" in text
    assert "15%" in text
    assert "3000 W" in text


def test_explanation_state_string_truncated_to_255() -> None:
    decision = MaestroDecision(
        phase="future_phase", reason="x" * 1000
    )
    coord = _make_coord(decision)
    text = _decision_explanation(coord)
    assert len(text) == 255
