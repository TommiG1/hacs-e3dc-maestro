"""Phase → full-sentence explanation for the Maestro control engine.

Kept in its own module (no Home Assistant dependencies) so it can be
unit-tested directly. The sensor platform delegates to ``decision_explanation``
to populate the ``decision_explanation`` sensor state.
"""
from __future__ import annotations

from typing import Any


def _f(value: Any, fmt: str = "{:.0f}", fallback: str = "—") -> str:
    """Format a possibly-None value with a fallback string."""
    if value is None:
        return fallback
    try:
        return fmt.format(value)
    except (TypeError, ValueError):
        return fallback


def decision_explanation(coord) -> str:
    """Build a German full-sentence explanation for the current control phase.

    Covers all 17 phases in :data:`const.ALL_PHASES`. Uses dynamic values from
    the last decision, current state and parameters where helpful. Falls back
    to the engine's own ``reason`` field for any unknown phase so new phases
    won't crash the sensor. Result is truncated to 255 chars (HA state limit).
    """
    dec = getattr(coord, "last_decision", None)
    if dec is None:
        return "Noch keine Entscheidung getroffen."

    state = None
    data = getattr(coord, "data", None)
    if data and isinstance(data, dict):
        state = data.get("state")
    p = getattr(coord, "_params", None)
    phase = dec.phase

    if phase == "off":
        text = (
            "Maestro-Regelung ist deaktiviert – es werden keine Steuerbefehle "
            "an den E3DC gesendet."
        )
    elif phase == "manual":
        text = (
            "Manueller Modus aktiv: Maestro greift nicht ein und überlässt die "
            "Steuerung dem Anwender."
        )
    elif phase == "idle":
        soc = _f(getattr(state, "soc", None))
        pv = _f(
            (state.pv_power / 1000) if state and state.pv_power is not None else None,
            "{:.1f}",
        )
        load = _f(
            (state.house_power / 1000)
            if state and state.house_power is not None
            else None,
            "{:.1f}",
        )
        text = (
            f"Aktuell kein Eingriff nötig: SoC liegt mit {soc}% im "
            f"Zielkorridor (PV {pv} kW, Last {load} kW)."
        )
    elif phase == "emergency":
        soc = _f(getattr(state, "soc", None))
        thr = _f(getattr(p, "charge_threshold", None))
        cpl = _f(dec.charge_power_limit)
        text = (
            f"Notladung aktiv: SoC {soc}% liegt unter der Ladeschwelle {thr}% – "
            f"Batterie wird mit {cpl} W priorisiert geladen."
        )
    elif phase == "feed_in_limit":
        excess = _f(dec.feed_in_excess_w)
        text = (
            f"Einspeisedrosselung greift: PV-Überschuss überschreitet das "
            f"Einspeiselimit um {excess} W – Batterie nimmt den Überschuss auf, "
            "statt ihn ans Netz zu verlieren."
        )
    elif phase == "reserve_protection":
        soc = _f(getattr(state, "soc", None))
        text = (
            f"Saisonale Notstromreserve geschützt: Batterie-Entladung ist "
            f"gesperrt, bis SoC {soc}% wieder über die saisonale "
            "Reserveschwelle steigt."
        )
    elif phase == "evcc_pause":
        mode = state.evcc_mode if state and state.evcc_mode else "now"
        text = (
            f"EVCC lädt das Auto gerade im Now-Modus ('{mode}') – "
            "Batterie-Entladung ist pausiert oder begrenzt, damit die "
            "Wallbox Vorrang hat."
        )
    elif phase == "ht_protection":
        text = (
            "Hochtarif-Schutz: Aktuell teurer Netzstromtarif – Maestro hält "
            "die Batterie für die HT-Phase bereit und sperrt günstiges "
            "Nachladen."
        )
    elif phase == "force_discharge":
        pw = _f(getattr(p, "force_discharge_power_w", None))
        text = (
            f"Manuelle Zwangs-Entladung über Dashboard-Schalter aktiv: "
            f"Batterie wird mit {pw} W entladen."
        )
    elif phase == "morning_discharge":
        target = _f(dec.target_soc)
        text = (
            f"Morgen-Vorentladung läuft: Batterie wird auf den Tagesziel-SoC "
            f"({target}%) entladen, damit der erwartete PV-Ertrag heute noch "
            "eingespeichert werden kann."
        )
    elif phase == "astro_wait":
        text = (
            "Warten auf Sonne: Vor dem Astro-Sonnenaufgangsfenster wird nicht "
            "aktiv geladen, um Eigenverbrauch zu maximieren."
        )
    elif phase == "morning_cap":
        until = _f(getattr(p, "morning_cap_until_h", None))
        cap = _f(getattr(p, "morning_cap_soc", None))
        text = (
            f"Morgen-SoC-Cap aktiv: Ladung wird bis {until} Uhr auf {cap}% "
            "begrenzt, damit ab Sonnenaufgang noch Aufnahmekapazität für PV "
            "bleibt."
        )
    elif phase == "hard_soc_limit":
        limit = _f(getattr(p, "hard_soc_limit", None))
        text = (
            f"Akku-Schonung: Fester Max-SoC-Deckel von {limit}% erreicht – "
            "Maestro stoppt das Nachladen oberhalb dieser Grenze."
        )
    elif phase == "corridor":
        target = _f(dec.target_soc)
        cpl = _f(dec.target_charge_power)
        text = (
            f"Saisonaler Ladekorridor: Ziel-SoC {target}% – Ladeleistung wird "
            f"auf {cpl} W dosiert, um den Korridor planmäßig zu erreichen."
        )
    elif phase == "pv_delay":
        rem = _f(getattr(state, "pv_forecast_remaining_kwh", None), "{:.1f}")
        text = (
            f"Vorausschauende Ladeverzögerung: PV-Prognose ({rem} kWh Rest "
            "heute) reicht aus – Maestro verschiebt die Ladung auf später."
        )
    elif phase == "spreading":
        cpl = _f(dec.target_charge_power)
        text = (
            f"Zeitbasierte Ladeverteilung aktiv: Ladeleistung wird auf {cpl} W "
            "gestreckt, um den Ziel-SoC gleichmäßig über das Tagesfenster zu "
            "erreichen."
        )
    elif phase == "curtailment_guard":
        cpl = _f(dec.charge_power_limit)
        text = (
            f"Abregelschutz aktiv: Batterie nimmt PV-Überschuss mit {cpl} W "
            "auf, um Wechselrichter-Drosselung zu vermeiden."
        )
    else:
        text = f"Phase {phase}: {dec.reason}"

    return text[:255]
