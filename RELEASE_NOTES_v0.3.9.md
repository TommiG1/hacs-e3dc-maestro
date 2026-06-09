# E3DC Maestro v0.3.9 – Schwacher-PV-Tag: Akku-Priorität

**Release-Typ:** Feature-Release  
**Datum:** 09.06.2026

---

## Übersicht

v0.3.9 erkennt **bewölkte oder schwache PV-Tage** anhand der Tagesprognose
(z. B. Solcast „Prognose heute“) und priorisiert an diesen Tagen die
**Akku-Ladung vor Netzeinspeisung**. Spreading-Drosselung und Korridor-Pause
werden umgangen; Maestro setzt **`NORMAL` + fester `max_charge`-Cap** – der
E3DC nutzt den PV-Überschuss selbst, ohne ständiges Nachregeln.

Typischer Anwendungsfall: An einem Tag mit nur ~50 % des erwarteten
Sommertags-Ertrags würde Maestro sonst im Korridor/Spreading drosseln und
Überschuss einspeisen — der Akku bleibt am Abend unter dem Ziel.

---

## ✨ Neues Feature: Schwacher-PV-Tag

### Erkennung

```
Quote = Tagesprognose (kWh) ÷ Referenz-Ertrag (kWh)
Schwacher Tag ⇔ Quote ≤ Schwelle (Standard: 0,5)
```

**Referenz-Ertrag** = Maximum aus:

- manueller Referenz (kWh, optional)
- installierte kWp × Faktor (Standard: 5,5 kWh/kWp)
- historischer Peak aus der PV-Statistik

Die **Tagesprognose wird einmal pro Tag** festgehalten (Latch), damit
nachmittägliche Solcast-Korrekturen die Strategie nicht hin- und herschalten.
**Schwelle und Referenz-Parameter** wirken **sofort** bei Änderung.

### Regelverhalten (wenn erkannt)

| Normal | Schwacher-PV-Tag |
|--------|------------------|
| SoC-Rampe begrenzt Ladeleistung | **`NORMAL` + fester `max_charge`-Cap** |
| Spreading drosselt auf Restzeit-Rate | Spreading aus |
| Korridor-Pause bei kleinem Überschuss | Pause umgangen |
| Maestro dosiert Ladeleistung pro Zyklus | E3DC nutzt PV-Überschuss selbst |

In der Entscheidungserklärung: `[Schwacher-PV-Tag: Überschuss-Priorität]`

### Finale Regelung

Bei aktivem Schwacher-PV-Tag und PV > 0:

- Modus **`NORMAL`** (kein Netzbezug – im Gegensatz zu `CHARGE`)
- Lade-Cap = **`max_charge_power`** (einmal gesetzt, kein Nachregeln pro Zyklus)
- Entspricht der bewährten **Korridor-7d-Logik** nach Ladeende-Stunde
- Anlauf-Ramp bei Low-Yield **aus**

### Regelungs-Fixes (Live-Betrieb)

Im Feld wurden mehrere Zwischenstände getestet. Finale Lösung:

| Problem | Zwischenversuch | Finaler Fix |
|---------|-----------------|-------------|
| EWMA-glättete Werte → Rest-Einspeisung (~300–500 W) | Momentan-Überschuss als Cap | Fester **`max_charge`-Cap** – Cap liegt immer über dem Surplus |
| E3DC lud unter engem Cap → Export | `CHARGE`-Modus | **`NORMAL`** – E3DC regelt Überschuss intern |
| `CHARGE` + `max_charge` → **Netzbezug** | – | **`NORMAL` + `max_charge`** – nur PV, kein Netzladen |
| Momentan-Cap pro Zyklus → Limit-Flackern | Hysterese 350 W | Fester Cap – Hysterese entfällt |

### Abgrenzung zu PV-Verzögerung

| Feature | Zweck |
|---------|--------|
| **PV-Verzögerung** | Bei *guter* Prognose Ladung *verschieben* |
| **Schwacher-PV-Tag** | Bei *schlechter* Prognose Akku *sofort* füllen |

---

## 🆕 Neue Entities

| Entity | Beschreibung |
|--------|--------------|
| `switch.e3dc_maestro_schwacher_pv_tag_prioritat` | Master-Schalter (Standard: an) |
| `binary_sensor.e3dc_maestro_schwacher_pv_tag` | Heute als schwacher Tag erkannt |
| `sensor.e3dc_maestro_pv_tagesprognose` | Gelatchte Tagesprognose (kWh) |
| `sensor.e3dc_maestro_pv_referenz_ertrag` | Berechneter Referenz-Ertrag (kWh) |
| `sensor.e3dc_maestro_pv_tag_quote` | Verhältnis Prognose ÷ Referenz |
| `number.e3dc_maestro_schwacher_pv_tag_schwelle` | Schwelle 0,1–1,0 (Standard: 0,5) |
| `number.e3dc_maestro_pv_referenz_manuell_0_automatisch` | Manuelle Referenz (0 = auto) |
| `number.e3dc_maestro_pv_referenz_faktor_kwh_kwp` | kWp-Faktor (Standard: 5,5) |

---

## 📋 Konfiguration (Upgrade)

Nach dem Update in den **Integrations-Optionen** (Bereich PV-Prognose):

1. **„Prognose heute – Tagessumme kWh“** setzen  
   z. B. `sensor.solcast_pv_forecast_prognose_heute`  
   *(ohne diesen Sensor bleiben Diagnose-Sensoren auf `unknown`)*

2. Optional: **Schwelle** anpassen  
   - `0,5` = Tag gilt als schwach ab ≤ 50 % Referenz  
   - Grenzfälle (z. B. 52 % bei Schwelle 0,5) → Schwelle z. B. auf `0,55` erhöhen

3. Integration **neu laden** oder HA **neustarten** (für neue Platform-Entities)

---

## 📊 Dashboard

`dashboards/maestro_dashboard.yaml` erweitert um:

- Tab **Übersicht**: Chip + Banner „Akku-Ladung priorisiert“
- Tab **Regelung**: Live-Tuning-Karte, Cockpit-Hinweise
- Tab **Laden**: Steuerung + Parameter
- Hilfe-Subview `/e3dc-maestro/help-low-yield` + Glossar-Eintrag

---

## ⚙️ Geänderte Dateien

- `control_engine.py` – `is_low_yield_day`, Korridor 6.96 (`NORMAL` + `max_charge`), Spreading-Hooks
- `coordinator.py` – Prognose-Latch, live Schwellen-Auswertung, Ramp-Bypass
- `consumption_stats.py` – `peak_daily_yield_kwh()`
- `const.py`, `config_flow.py`, `switch.py`, `number.py`, `sensor.py`, `binary_sensor.py`
- `explanation.py`, `strings.json`, `translations/de.json`
- `dashboards/maestro_dashboard.yaml`
- `tests/test_control_engine.py` – TestLowYield* (+19 Tests)

---

## 🧪 Tests

305 Tests bestanden (inkl. neuer Low-Yield-Tests).

---

## ⚠️ Breaking Changes

Keine. Bestehende Installationen: Feature standardmäßig **aktiv**; ohne
konfigurierten Prognose-Sensor greift die Erkennung nicht (kein Fehler).

---
---

# E3DC Maestro v0.3.9 – Low-Yield Day: Battery Priority

**Release type:** Feature release  
**Date:** 2026-06-09

---

## Overview

v0.3.9 detects **cloudy or low-PV days** using the daily yield forecast
(e.g. Solcast “Forecast today”) and on those days **prioritises battery
charging over grid export**. Spreading throttling and corridor pause are
bypassed; Maestro sets **`NORMAL` + fixed `max_charge` cap** – the E3DC
routes PV surplus to the battery autonomously, without per-cycle retuning.

Typical use case: on a day with only ~50 % of the expected sunny-day yield,
Maestro would otherwise throttle in corridor/spreading mode and export surplus
power — leaving the battery below target by evening.

---

## ✨ New feature: Low-yield day

### Detection

```
Ratio = daily forecast (kWh) ÷ reference yield (kWh)
Low-yield day ⇔ ratio ≤ threshold (default: 0.5)
```

**Reference yield** = maximum of:

- manual reference (kWh, optional)
- installed kWp × factor (default: 5.5 kWh/kWp)
- historical peak from PV statistics

The **daily forecast is latched once per day** so afternoon Solcast updates
do not flip strategy back and forth. **Threshold and reference parameters**
apply **immediately** when changed.

### Control behaviour (when active)

| Normal | Low-yield day |
|--------|----------------|
| SoC ramp limits charge power | **`NORMAL` + fixed `max_charge` cap** |
| Spreading throttles to time-spread rate | Spreading off |
| Corridor pause on small surplus | Pause bypassed |
| Maestro retunes charge power each cycle | E3DC routes PV surplus autonomously |

Decision explanation includes: `[Low-yield day: surplus priority]`

### Final control behaviour

When low-yield is active and PV > 0:

- Mode **`NORMAL`** (no grid import – unlike `CHARGE`)
- Charge cap = **`max_charge_power`** (set once, no per-cycle retuning)
- Same pattern as proven **corridor 7d** logic after charge-end hour
- Charge ramp **bypassed** on low-yield days

### Control fixes (field operation)

Several intermediate builds were tested in the field. Final solution:

| Issue | Intermediate attempt | Final fix |
|-------|---------------------|-----------|
| EWMA-smoothed values → residual export (~300–500 W) | Instant surplus as cap | Fixed **`max_charge` cap** – cap always above surplus |
| E3DC charged below tight cap → export | `CHARGE` mode | **`NORMAL`** – E3DC manages surplus internally |
| `CHARGE` + `max_charge` → **grid import** | – | **`NORMAL` + `max_charge`** – PV only, no grid charging |
| Per-cycle instant cap → limit flicker | 350 W hysteresis | Fixed cap – hysteresis removed |

### vs. PV delay

| Feature | Purpose |
|---------|---------|
| **PV delay** | *Defer* charging when forecast is *good* |
| **Low-yield day** | *Fill battery immediately* when forecast is *poor* |

---

## 🆕 New entities

| Entity | Description |
|--------|-------------|
| `switch.e3dc_maestro_schwacher_pv_tag_prioritat` | Master switch (default: on) |
| `binary_sensor.e3dc_maestro_schwacher_pv_tag` | Low-yield day detected today |
| `sensor.e3dc_maestro_pv_tagesprognose` | Latched daily forecast (kWh) |
| `sensor.e3dc_maestro_pv_referenz_ertrag` | Computed reference yield (kWh) |
| `sensor.e3dc_maestro_pv_tag_quote` | Forecast ÷ reference ratio |
| `number.e3dc_maestro_schwacher_pv_tag_schwelle` | Threshold 0.1–1.0 (default: 0.5) |
| `number.e3dc_maestro_pv_referenz_manuell_0_automatisch` | Manual reference (0 = auto) |
| `number.e3dc_maestro_pv_referenz_faktor_kwh_kwp` | kWp factor (default: 5.5) |

*Entity IDs use German slugs; friendly names are localised via translations.*

---

## 📋 Configuration (upgrade)

After updating, in **integration options** (PV forecast section):

1. Set **“Forecast today – daily total kWh”**  
   e.g. `sensor.solcast_pv_forecast_prognose_heute`  
   *(without this sensor, diagnostic entities stay `unknown`)*

2. Optionally tune **threshold**  
   - `0.5` = low-yield when forecast ≤ 50 % of reference  
   - Borderline cases (e.g. 52 % with threshold 0.5) → raise to e.g. `0.55`

3. **Reload** the integration or **restart** HA (for new platform entities)

---

## 📊 Dashboard

`dashboards/maestro_dashboard.yaml` extended with:

- **Overview** tab: chip + banner “Battery charging prioritised”
- **Control** tab: live-tuning card, cockpit hints
- **Charging** tab: controls + parameters
- Help subview `/e3dc-maestro/help-low-yield` + glossary entry

---

## ⚙️ Changed files

- `control_engine.py` – `is_low_yield_day`, corridor 6.96 (`NORMAL` + `max_charge`), spreading hooks
- `coordinator.py` – forecast latch, live threshold evaluation, ramp bypass
- `consumption_stats.py` – `peak_daily_yield_kwh()`
- `const.py`, `config_flow.py`, `switch.py`, `number.py`, `sensor.py`, `binary_sensor.py`
- `explanation.py`, `strings.json`, `translations/de.json`
- `dashboards/maestro_dashboard.yaml`
- `tests/test_control_engine.py` – TestLowYield* (+19 tests)

---

## 🧪 Tests

305 tests passed (including new low-yield tests).

---

## ⚠️ Breaking changes

None. Existing installs: feature **enabled** by default; without a configured
forecast sensor, detection stays inactive (no error).
