# E3DC Maestro v0.3.11 – Bugfix: Korridor-Snapshot blockierte PV-Überschuss-Ladung

**Release-Typ:** Bugfix-Release
**Datum:** 2026-06-21

---

## Übersicht

v0.3.11 behebt einen kritischen Regelungs-Bug, bei dem die E3DC stundenlang
mit einem winzigen Lade-Cap (z. B. **51 W**) festsaß, obwohl der Soll-Wert
intern bereits auf ~**2 kW** angewachsen war. In der Folge wurde
PV-Überschuss (~14 kW) ins Netz exportiert, statt den Akku zu laden —
sichtbar an einem stagnierenden SoC trotz Sonnenschein.

Ergänzend sind zwei neue Diagnose-Sensoren hinzugekommen, die das tatsächlich
an die E3DC gesendete Cap zeigen (statt nur den intern berechneten Soll-Wert).

---

## 🐛 Behobene Fehler

### 1. Debounce verglich Soll vs. Soll statt Soll vs. zuletzt gesendet (kritisch)

**Symptom:** Korridor sendet einmal ein winziges Cap (~51 W), danach wächst
der interne Soll-Wert über die Rampe auf ~2 kW an — aber jede neue
RSCP-Übertragung wird durch den Debounce blockiert. Die E3DC bleibt
stundenlang am 51-W-Cap hängen.

**Ursache:** `coordinator._async_act` verglich die aktuelle Entscheidung mit
der vorherigen Entscheidung (`prev.last_decision`). Bei einer langsamen
Rampe ist die Differenz pro Zyklus < 50 W (Debounce-Schwelle), also wurde
nie neu gesendet. Der tatsächlich an die E3DC gesendete Cap-Wert wurde
nirgends gespeichert.

**Fix:** Neue Felder `_last_sent_charge_limit` / `_last_sent_discharge_limit`
halten das zuletzt per `e3dc_rscp` gesendete Cap. Die Debounce-Funktion
`_limits_changed_vs_sent_values` vergleicht jetzt Soll vs. **gesendet** statt
Soll vs. vorherige Entscheidung. Die Felder werden bei jedem RSCP-Send
aktualisiert und bei `clear_power_limits` / `_async_release_limits` auf
`None` zurückgesetzt.

### 2. Korridor-Dip bei Interim-Ziel sendet 51-W-Snapshot

**Symptom:** Bei `advanced_corridor=true` mit `lower_corridor=50` und
`min_charge_power=50` liefert ein winziges `soc_delta` (Interim-Ziel ≈
aktueller SoC, z. B. 47 → 47 %) ein Soll-Cap knapp über `lower_corridor`.
Da Spreading-aktiv den `lower_corridor_pause`-Guard umgeht, fließt dieser
51-W-Snapshot bis zur nächsten Phasen-Aktion an die E3DC und verdeckt die
echte Spreading-Rate (~2 kW) für mehrere Minuten.

**Fix:** `desired_charge_power` prüft im `advanced_corridor`-Modus den
Spielraum oberhalb des `lower_corridor`-Ankers (`raw_above_corridor`) und
gibt **0 W** zurück, sobald dieser unter `min_charge_power` liegt. Damit
überspringt der Korridor-Block in `decide()` den Snapshot-Send und Phase 8
Spreading liefert die zeitbasierte Rate. Größere `soc_delta`-Fälle und der
Default-Modus (time-to-target) bleiben unverändert.

### 3. NORMAL-Modus sendete unnötiges `power_value`

**Symptom:** Bei `power_mode=NORMAL` mit gesetztem Lade-Cap wurden sowohl
`set_power_limits` (`max_charge`) als auch `set_power_mode`
(`power_value=<charge_power_limit>`) an `e3dc_rscp` gesendet. `power_value`
ist semantisch nur für CHARGE/DISCHARGE gedacht; im Feld führte das
zusätzliche Feld bei manchen Firmwares zu unklarem Verhalten.

**Fix:** Neue Hilfsfunktion `_build_power_mode_data` setzt `power_value` nur
noch für CHARGE/DISCHARGE. NORMAL und IDLE senden ausschließlich `power_mode`.
Das Lade-Cap wird unverändert per `set_power_limits` übertragen.

### 4. Anlauf-Rampe verlor mehrere Minuten nach Phasenwechsel

**Symptom:** Nach einem Korridor-Dip oder Phasenwechsel ramped die Hardware
mit `charge_ramp_w_per_cycle=200` und 10-s-Zyklen rund **100 s** lang hoch,
bis das Cap wieder beim echten Bedarf (~2 kW) ankommt — in dieser Zeit
exportiert die Anlage PV-Überschuss ins Netz.

**Fix:** Neuer Resync-Bypass `_ramp_bypass_due_to_resync`: Wenn die Differenz
zwischen Soll und zuletzt gesendetem Cap größer ist als `max(500, 2 ×
charge_ramp_w_per_cycle)`, wird die Rampe für diesen Zyklus übersprungen.
Reguläres Hochrampen aus dem Stand bleibt unverändert.

### 5. Entlade-Limit fehlte bei Korridor-Ladung

**Symptom:** Soll- und Gesendet-Entlade-Limit blieben leer (`unknown`), obwohl
der Akku laden sollte. Die E3DC konnte weiter `unloading_blocked=ON` melden,
weil nach EVCC oder früheren Sperren kein neues `max_discharge` gesendet wurde.
Beim ersten Fix wurde fälschlich die **WR-Nennleistung** (z. B. 18 kW) statt
der **Max. Ladeleistung** (z. B. 9 kW) als freies Entlade-Cap übertragen.

**Fix:** Bei aktivem Lade-Cap sendet Maestro jetzt zusätzlich
`max_discharge = max_charge_power` (nicht `inverter_power`), damit Entladung
zum Hausverbrauch explizit freigegeben wird und frühere Entladesperren
überschrieben werden. Neue Hilfsfunktion `_effective_discharge_limit_w`;
Debounce vergleicht das effektive Entlade-Cap.

---

## 📊 Dashboard

`dashboards/maestro_dashboard.yaml` und `dashboards/e3dc_maestro.yaml`:

- Übersicht und Cockpit: Kacheln **Soll** vs. **Gesendet** (Lade- und Entlade-Limit)
- Orange Markierung bei Drift > 50 W zwischen Soll und Gesendet
- Diagnose-Tab: neue Limit-Sensoren
- Hilfe Steuerverhalten: Erklärung Soll/Gesendet und Entlade-Cap

Nach Update: Integration neu laden oder HA neustarten (neue Sensoren), Dashboard
Hard-Refresh im Browser.

---

## 🆕 Neue Entities

| Entity | Beschreibung |
|--------|--------------|
| `sensor.e3dc_maestro_gesendetes_lade_limit` | Lade-Cap (W), das zuletzt an die E3DC gesendet wurde |
| `sensor.e3dc_maestro_gesendetes_entlade_limit` | Entlade-Cap (W), das zuletzt an die E3DC gesendet wurde |

Diese Sensoren machen den Soll-vs-Ist-Drift sichtbar — falls Soll und
Gesendet auseinanderlaufen, weiß man sofort, ob der Debounce greift oder
ein Send-Fehler vorliegt.

## ✏️ Umbenannte Entities

| Entity-ID (bleibt) | Alt | Neu |
|--------------------|-----|-----|
| `sensor.e3dc_maestro_aktives_lade_limit` | Aktives Lade-Limit | **Soll-Lade-Limit** |
| `sensor.e3dc_maestro_aktives_entlade_limit` | Aktives Entlade-Limit | **Soll-Entlade-Limit** |

Die Sensoren zeigten schon immer den von Maestro berechneten Soll-Wert
(nicht das tatsächlich an die E3DC gesendete Cap). Der neue Name macht
das klar.

---

## 📊 Erweiterte Attribute

`sensor.e3dc_maestro_letzte_aktion` und `sensor.e3dc_maestro_entscheidungserklarung`
enthalten neu:

- `sent_charge_power_limit`
- `sent_discharge_power_limit`

---

## ⚙️ Geänderte Dateien

- `custom_components/e3dc_maestro/coordinator.py` — Debounce vs. gesendet,
  Resync-Bypass, `_build_power_mode_data`, `last_sent_*`-Properties
- `custom_components/e3dc_maestro/control_engine.py` — Korridor-Dip-Schutz
  in `desired_charge_power`
- `custom_components/e3dc_maestro/sensor.py` — neue Sensoren, Umbenennung,
  erweiterte Attribute
- `custom_components/e3dc_maestro/strings.json`,
  `translations/de.json` — neue Namen
- `custom_components/e3dc_maestro/manifest.json` — Version
- `dashboards/maestro_dashboard.yaml`, `dashboards/e3dc_maestro.yaml` —
  Soll/Gesendet-Kacheln, Drift-Anzeige
- `tests/test_coordinator_debounce.py`,
  `tests/test_control_engine.py` — 19 neue Tests

---

## 🧪 Tests

324 Tests bestanden (19 neue für die Bugfixes).

---

## ⚠️ Breaking Changes

Keine. Die Entity-IDs der umbenannten Sensoren bleiben für bestehende
Installationen unverändert; nur die Anzeigenamen wechseln. Bestehende
Dashboards funktionieren weiter.

---
---

# E3DC Maestro v0.3.11 – Bugfix: Corridor snapshot blocked PV surplus charging

**Release type:** Bugfix release
**Date:** 2026-06-21

---

## Overview

v0.3.11 fixes a critical control bug where the E3DC could remain stuck on a
tiny charge cap (e.g. **51 W**) for hours while the internal target had
already grown to ~**2 kW**. As a result, PV surplus (~14 kW) was exported to
the grid instead of charging the battery — visible as a stagnant SoC despite
sunshine.

Two new diagnostic sensors expose the cap actually sent to the E3DC (instead
of only the internally computed target).

---

## 🐛 Fixed issues

### 1. Debounce compared target vs. target instead of target vs. last sent (critical)

**Symptom:** The corridor sends a tiny initial cap (~51 W); the internal
target ramps up to ~2 kW, but every subsequent RSCP send is blocked by the
debounce. The E3DC stays stuck at the 51 W cap for hours.

**Cause:** `coordinator._async_act` compared the current decision against
the previous decision (`prev.last_decision`). With a slow ramp, the
per-cycle delta stays below the 50 W debounce threshold, so no new send
ever happens. The value actually transmitted to the E3DC was never tracked.

**Fix:** New fields `_last_sent_charge_limit` /
`_last_sent_discharge_limit` track the last cap sent via `e3dc_rscp`. The
debounce function `_limits_changed_vs_sent_values` now compares target vs.
**sent** instead of target vs. previous decision. The fields are updated on
every RSCP send and reset to `None` on `clear_power_limits` /
`_async_release_limits`.

### 2. Corridor dip at interim target sent a 51 W snapshot

**Symptom:** With `advanced_corridor=true`, `lower_corridor=50` and
`min_charge_power=50`, a tiny `soc_delta` (interim target ≈ current SoC,
e.g. 47 → 47 %) yields a target cap just above `lower_corridor`. Because
active spreading bypasses the `lower_corridor_pause` guard, this 51 W
snapshot reaches the E3DC and masks the real spreading rate (~2 kW) for
several minutes.

**Fix:** `desired_charge_power` checks the headroom above the
`lower_corridor` anchor (`raw_above_corridor`) in `advanced_corridor` mode
and returns **0 W** whenever it falls below `min_charge_power`. The
corridor block in `decide()` is then skipped and Phase 8 spreading provides
the time-based rate. Larger `soc_delta` cases and the default mode
(time-to-target) are untouched.

### 3. NORMAL mode sent unnecessary `power_value`

**Symptom:** With `power_mode=NORMAL` and a charge cap set, both
`set_power_limits` (`max_charge`) and `set_power_mode`
(`power_value=<charge_power_limit>`) were sent to `e3dc_rscp`. `power_value`
is semantically intended for CHARGE/DISCHARGE only; in the field some
firmwares behaved inconsistently with the extra field.

**Fix:** New helper `_build_power_mode_data` attaches `power_value` only for
CHARGE/DISCHARGE. NORMAL and IDLE send `power_mode` only. The charge cap
itself is still sent via `set_power_limits`.

### 4. Charge ramp wasted minutes after phase changes

**Symptom:** After a corridor dip or phase change, the hardware ramped at
`charge_ramp_w_per_cycle=200` and 10 s ticks for around **100 s** until the
cap caught up with the real demand (~2 kW). PV surplus exported to grid
during that time.

**Fix:** New resync bypass `_ramp_bypass_due_to_resync`: if the gap between
target and last sent cap exceeds `max(500, 2 × charge_ramp_w_per_cycle)`,
the ramp is skipped for this cycle. Regular ramp-up from cold start is
unchanged.

### 5. Discharge limit missing during corridor charging

**Symptom:** Target and sent discharge limits stayed empty (`unknown`) even
while the battery should charge. The E3DC could keep reporting
`unloading_blocked=ON` because no new `max_discharge` was sent after EVCC or
earlier blocks. An initial fix incorrectly used **inverter rated power**
(e.g. 18 kW) instead of **max charge power** (e.g. 9 kW) as the free
discharge cap.

**Fix:** When a charge cap is active, Maestro now also sends
`max_discharge = max_charge_power` (not `inverter_power`) so house discharge
is explicitly allowed and stale discharge blocks are cleared. New helper
`_effective_discharge_limit_w`; debounce compares the effective discharge cap.

---

## 📊 Dashboard

`dashboards/maestro_dashboard.yaml` and `dashboards/e3dc_maestro.yaml`:

- Overview and cockpit: **target** vs. **sent** tiles (charge and discharge limits)
- Orange highlight when target vs. sent drift exceeds 50 W
- Diagnostics tab: new limit sensors
- Steuerverhalten help: target/sent explanation and discharge cap notes

After updating: reload the integration or restart HA (new sensors), hard-refresh
the dashboard in your browser.

---

## 🆕 New entities

| Entity | Description |
|--------|-------------|
| `sensor.e3dc_maestro_gesendetes_lade_limit` | Charge cap (W) most recently sent to the E3DC |
| `sensor.e3dc_maestro_gesendetes_entlade_limit` | Discharge cap (W) most recently sent to the E3DC |

These sensors surface the target-vs-sent drift directly — if they diverge,
you can immediately tell whether the debounce is guarding the send or
something else is wrong.

## ✏️ Renamed entities

| Entity ID (unchanged) | Old | New |
|-----------------------|-----|-----|
| `sensor.e3dc_maestro_aktives_lade_limit` | Aktives Lade-Limit | **Soll-Lade-Limit** |
| `sensor.e3dc_maestro_aktives_entlade_limit` | Aktives Entlade-Limit | **Soll-Entlade-Limit** |

These sensors always reflected the Maestro-computed target (not the cap
actually sent to the E3DC). The new name makes that explicit.

---

## 📊 Extended attributes

`sensor.e3dc_maestro_letzte_aktion` and `sensor.e3dc_maestro_entscheidungserklarung`
now include:

- `sent_charge_power_limit`
- `sent_discharge_power_limit`

---

## ⚙️ Changed files

- `custom_components/e3dc_maestro/coordinator.py` — debounce vs. sent,
  resync bypass, `_build_power_mode_data`, `last_sent_*` properties
- `custom_components/e3dc_maestro/control_engine.py` — corridor dip
  protection in `desired_charge_power`
- `custom_components/e3dc_maestro/sensor.py` — new sensors, rename,
  extended attributes
- `custom_components/e3dc_maestro/strings.json`,
  `translations/de.json` — new names
- `custom_components/e3dc_maestro/manifest.json` — version
- `dashboards/maestro_dashboard.yaml`, `dashboards/e3dc_maestro.yaml` —
  target/sent tiles, drift highlight
- `tests/test_coordinator_debounce.py`,
  `tests/test_control_engine.py` — 19 new tests

---

## 🧪 Tests

324 tests passed (19 new tests for the bugfixes).

---

## ⚠️ Breaking changes

None. Existing installations keep their entity IDs (only the display names
of the renamed sensors change). Dashboards continue to work unchanged.
