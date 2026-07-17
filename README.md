🇬🇧 English | [🇩🇪 Deutsch](README.de.md)

# E3DC Maestro

A Home Assistant custom integration for **intelligent, fully automated charge and discharge control** of E3DC home battery systems.

E3DC Maestro runs entirely **local and without any cloud connection**. It extends the `e3dc_rscp` integration with a rule-based control engine featuring 17 prioritised phases, forward-looking charging, curtailment guard, PV forecast, tariff-aware spreading, wallbox and heat-pump control, and an auto-optimisation mode.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg?style=for-the-badge)](LICENSE)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue?style=for-the-badge&logo=paypal)](https://www.paypal.com/paypalme/tommigraf)

---

## Table of Contents

1. [Feature Overview](#feature-overview)
2. [Screenshots](#screenshots)
3. [Requirements](#requirements)
4. [Dependency: configure e3dc_rscp](#dependency-configure-e3dc_rscp)
5. [Installation via HACS](#installation-via-hacs)
6. [Setup (Config Flow)](#setup-config-flow)
7. [Provided Entities](#provided-entities)
   - [Sensors – Standard (enabled)](#sensors--standard-enabled)
   - [Sensors – Diagnostic (enable manually)](#sensors--diagnostic-enable-manually)
   - [How to enable disabled entities](#how-to-enable-disabled-entities)
   - [Binary Sensors](#binary-sensors)
   - [Switches](#switches)
   - [Numbers](#numbers)
   - [Selects](#selects)
   - [Buttons](#buttons)
8. [Rule Logic & Phase Priority](#rule-logic--phase-priority)
9. [Import Dashboard](#import-dashboard)
10. [Sensor Sign Conventions](#sensor-sign-conventions)
11. [Troubleshooting & FAQ](#troubleshooting--faq)
12. [Known Compatibility](#known-compatibility)
13. [Acknowledgements](#acknowledgements)
14. [Changelog](CHANGELOG.md)
15. [License](#license)

---

## Feature Overview

| Feature | Description |
|---|---|
| **Seasonal charge corridor** | Rolling daily target and charge window interpolated between summer and winter |
| **Feed-in limit protection** | Reactively raises charge power when grid export exceeds the 70 % limit |
| **Curtailment guard** | Preventive minimum charge power when inverter clipping is imminent |
| **Emergency reserve** | Seasonally interpolated or consumption-adaptive battery reserve |
| **Peak-tariff (HT) protection** | Blocks discharge during configured high-tariff hours |
| **PV forecast delay** | Delays corridor charging when Solcast/Forecast.Solar predicts enough PV |
| **Forward-looking charging** | Raises today's charge target when tomorrow's PV is expected to be low |
| **Spreading (charge distribution)** | Spreads PV surplus evenly across the remaining charge window – **default ON since v0.3.1** (hardware protection against 0/max-power bursts) |
| **Morning pre-discharge** | Discharges the battery in the morning to free up capacity for daytime PV |
| **Astro mode** | Dynamically links charge end / charge start to sunset / sunrise |
| **Morning cap** | SoC ceiling in the morning so the battery doesn't fill up too early |
| **Hard SoC limit** | Fixed charge ceiling for battery health (independent of all other phases) |
| **Auto-optimisation** | Grid-search optimiser automatically selects the best daily strategy |
| **24 h forecast simulation** | Predicted SoC trajectory as an ApexCharts sensor |
| **Dynamic tariffs** | Grid charging at low spot prices (Tibber, aWATTar) |
| **Tariff slots** | Fixed time windows with custom charge/discharge rules |
| **Wallbox control** | Current limiting for third-party wallboxes via EVCC/generic |
| **Heat-pump control** | On/off based on PV surplus with minimum run and pause times |
| **Forced discharge** | Dashboard switch for manual discharge, e.g. before a Tibber low-price window |
| **Control cockpit** | Live command centre with hero status, KPI tiles, active-now chips, 24 h phase history and "Why this decision?" |
| **Decision explanation** | `decision_explanation` sensor with a full plain-text explanation for every phase |
| **Anti-flapping** | EWMA smoothing of PV/load (τ = 60 s, jump-reset at 2 kW) + feed-in-limit hysteresis + pv-delay cooldown to prevent rapid phase oscillation |
| **Battery & PV Sizing Advisor (v0.3.7)** | 2D simulation (additional battery × additional PV) on historical hourly data — calculates savings, payback time, self-sufficiency and three recommendations (economic / technical / balanced) |
| **287 automated tests** | Control engine, forecast simulator, optimiser and sizing advisor fully covered |

---

## Screenshots

### Tab 1 – Dashboard & Live Overview
![Dashboard Overview](Screenshots/01_dashboard_uebersicht.png)

### Tab 2 – Charging & Charge Strategy
![Charging & Strategy](Screenshots/02_laden_ladestrategie.png)

### Tab 3 – Scheduling & Astro Mode
![Scheduling & Astro](Screenshots/03_zeitplanung_astro.png)

### Tab 4 – Grid & Tariff
![Grid & Tariff](Screenshots/04_netz_tarif.png)

### Tab 5 – Flexibility (Wallbox, Heat Pump, Pre-Discharge)
![Flexibility](Screenshots/05_flexibilitaet_wallbox.png)

### Tab 6 – Settings & System Parameters
![Settings](Screenshots/06_einstellungen_system.png)

### Tab 7 – Diagnostics & Debug
![Diagnostics](Screenshots/07_diagnose.png)

### Tab 8 – Help & Glossary
![Help](Screenshots/08_hilfe_glossar.png)

### Tab 9 – Auto-Optimisation
![Auto-Optimisation](Screenshots/09_auto_optimierung.png)

### Tab 10 – Battery & PV Sizing Advisor (v0.3.7)

New tab: 2D historical simulation, scenario sliders (additional battery / PV),
live KPIs (self-sufficiency, avoided grid import, savings, investment, payback),
three recommendation strategies and editable cost inputs.

---

## Requirements

| Requirement | Details |
|---|---|
| **Home Assistant** | ≥ 2024.1.0 (recommended: ≥ 2024.11) |
| **HACS** | latest version |
| **[e3dc_rscp](https://github.com/torbennehmer/hacs-e3dc)** | must be installed, configured and active |
| **E3DC device** | All E3DC systems supported by `e3dc_rscp` (tested: S10E, S10E Pro) |
| **Solcast / Forecast.Solar** | optional but recommended for PV forecast features (forward-looking charge, PV delay) |

> **Important:** E3DC Maestro reads sensors from `e3dc_rscp` and calls its services (`set_power_limits`, `set_power_mode`, `manual_charge`). Without a working and correctly configured `e3dc_rscp` integration, Maestro **cannot control** the battery.

> **⚠️ AI360 must be disabled:** E3DC's built-in **AI360** function must be disabled in the E3DC device settings. AI360 overrides external charge commands and ignores Maestro's rules — both systems cannot run simultaneously. The setting is in the E3DC web interface or E3DC app under *Settings → Energy Management → AI360*.

---

## Dependency: configure e3dc_rscp

Before setting up E3DC Maestro, `e3dc_rscp` must be **correctly configured**. Incorrect sensor signs are the most common cause of misbehaviour.

### 1. Verify sign conventions

Maestro expects the following sign convention:

| Sensor | Positive | Negative |
|---|---|---|
| `grid_power_sensor` | Export to grid | Import from grid |
| `battery_power_sensor` | Battery charging | Battery discharging |
| `pv_power_sensor` | always ≥ 0 | – |
| `house_power_sensor` | always ≥ 0 | – |

**How to check:** Open *Developer Tools → States* in HA and observe values while PV is producing:
- PV sensor: must be positive (~4000 W at noon)
- Grid sensor: positive when exporting, negative when importing
- Battery sensor: positive while charging, negative while discharging

**If signs are inverted**, create a template sensor (e.g. in `configuration.yaml`):

```yaml
template:
  - sensor:
      - name: "E3DC Grid corrected"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.your_grid_sensor') | float(0)) }}"
```

Restart HA after changes.

---

## Installation via HACS

### Step 1: Add repository

1. Open **HACS** → Integrations → three-dot menu (top right) → **Custom repositories**
2. Enter URL: `https://github.com/TommiG1/hacs-e3dc-maestro`
3. Category: **Integration** → **Add**

### Step 2: Download integration

1. Search for **E3DC Maestro** in the HACS integration list
2. Click **Download** → confirm version

### Step 3: Restart Home Assistant

Settings → System → **Restart** (full restart, not just reload)

### Step 4: Set up integration

1. **Settings → Devices & Services → Add Integration**
2. Search for **E3DC Maestro**
3. Follow the setup wizard (see next section)

> **Note:** If E3DC Maestro doesn't appear in the search, clear the browser cache (Ctrl+Shift+R) and try again.

---

## Setup (Config Flow)

The setup wizard has **11 steps**. All parameters can be changed at any time under **Settings → Devices & Services → E3DC Maestro → Configure** — no restart required.

> **Since v0.3.7:** the Configure dialog opens with a **central navigation menu**.
> You can jump directly to any section (sources, system, season, tariff, wallbox,
> heat pump, sizing advisor, …) instead of clicking through all steps in order.
> After editing a section you return to the menu and can either edit another
> section or close the dialog via **Save & Close**.

---

### Step 1: Source entities

Maps Maestro to the sensor entities from `e3dc_rscp` (or Modbus).

> **✨ Auto-detection:** If `e3dc_rscp` is installed, Maestro pre-fills all sensors
> (SoC, PV, house, grid, battery, wallbox consumption) and inverts the grid sign for
> `_transfer_to_from_grid` automatically. An **openWB** wallbox is detected via
> `sensor.openwb_chargepoint*_ladeleistung`, and an existing **EVCC integration**
> ([marq24/ha-evcc](https://github.com/marq24/ha-evcc), domain `evcc_intg`) is detected
> as well. All suggestions can be overridden.

| Field | Required | Typical Entity ID | Convention |
|---|---|---|---|
| **State of Charge (SoC)** | ✓ | `sensor.<devicename>_battery_rsoc` | 0–100 % |
| **PV power** | ✓ | `sensor.<devicename>_solar_power` | W, ≥ 0 |
| **Additional generation** | – | – | W, ≥ 0, added to PV (e.g. second inverter) |
| **House power** | ✓ | `sensor.<devicename>_home_power` | W, ≥ 0 |
| **Grid power** | ✓ | `sensor.<devicename>_grid_power` | W, **positive = export** |
| **Battery power** | ✓ | `sensor.<devicename>_battery_power` | W, **positive = charging, negative = discharging** |
| **Charged today (kWh)** | – | `sensor.<devicename>_battery_charge_today` | kWh (RSCP daily value, more accurate than Riemann sum) |
| **Discharged today (kWh)** | – | `sensor.<devicename>_battery_discharge_today` | kWh (RSCP daily value) |

> **Tip:** `<devicename>` is the name you gave when setting up `e3dc_rscp`. Find exact entity IDs under *Developer Tools → States* — search for `battery_rsoc`, `solar_power`, `grid_power`.

---

### Step 2: System parameters

Describes your system hardware.

| Parameter | Default | Description |
|---|---|---|
| **Inverter rated power (W)** | 12 000 | Maximum AC output power of the inverter |
| **Installed PV capacity (kWp)** | 10.0 | Used for feed-in limit and forecast calculations |
| **Max. charge power (W)** | 3 000 | Upper limit for battery charge commands |
| **Min. charge power (W)** | 300 | Lower limit; below this no charging command is sent |
| **Feed-in limit (%)** | 70 | % of installed kWp — `feed_in_limit` phase triggers above this |
| **Update interval (s)** | 30 | How often Maestro decides; shorter intervals increase DB load |
| **Advanced corridor** | off | If on: charge power directly in W instead of power factor |
| **Lower corridor (W)** | 500 | Minimum charge power in advanced corridor mode |
| **Upper corridor (W)** | 1 500 | Maximum charge power in advanced corridor mode |
| **Charge ramp (W/cycle)** | 500 | Ramp: charge power increases by at most this value per cycle |

---

### Step 3: Season & charge corridor

Defines when and to what SoC target the battery is charged each day.

| Parameter | Default | Description |
|---|---|---|
| **Charge threshold (%)** | 15 | SoC floor for emergency charging (`emergency` phase) |
| **Charge target SoC (%)** | 85 | Daily target SoC for the seasonal corridor |
| **Winter minimum charge end (h)** | 11:00 | Earliest charge end in winter (local time) |
| **Summer maximum charge end (h)** | 14:00 | Latest charge end in summer (local time) |
| **Summer charge end target (h)** | 18:30 | Battery should be fully charged by this time in summer |

Maestro calculates the optimal charge window **daily** (based on the current date) by interpolating between the summer and winter values.

---

### Step 4: Peak-tariff (HT) protection

Prevents battery discharge during expensive peak-tariff hours.

| Parameter | Default | Description |
|---|---|---|
| **HT protection enabled** | off | Enables all HT logic |
| **Peak tariff start (h)** | 6 | Local time (CET/CEST automatically) |
| **Peak tariff end (h)** | 21 | Local time |
| **Reserve winter (%)** | 50 | Minimum SoC kept during HT window (winter) |
| **Reserve equinox (%)** | 10 | Minimum SoC at equinox |
| **HT on Saturdays** | off | HT protection also applies on Saturdays |
| **HT on Sundays** | off | HT protection also applies on Sundays |

---

### Step 5: PV forecast / charge delay

Delays the corridor charge start if today's remaining PV forecast is sufficient to fill the battery later.

| Parameter | Default | Description |
|---|---|---|
| **PV forecast delay** | off | Enables `pv_delay` phase |
| **Forecast sensor** | – | Entity ID of a sensor providing remaining PV kWh today |
| **Min. forecast (kWh)** | 5.0 | Absolute threshold: only delay if forecast ≥ this value |
| **Usable battery capacity (kWh)** | 10.0 | How many kWh the battery still needs to reach target SoC |
| **Safety factor** | 1.2 | Forecast must be ≥ required × factor |
| **Tomorrow PV sensor** | – | For forward-looking charging: tomorrow's PV forecast (kWh) |
| **Tomorrow consumption sensor** | – | For forward-looking charging: estimated consumption tomorrow (kWh) |

**Recommended forecast integrations (HACS):**
- [Solcast PV Forecast](https://github.com/BJReplay/ha-solcast-solar): `sensor.solcast_pv_forecast_forecast_today_remaining` / `sensor.solcast_pv_forecast_forecast_tomorrow`
- [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/): `sensor.energy_production_today_remaining`

---

### Step 6: Dynamic tariffs & tariff slots

Charges the battery from the grid when the spot electricity price is cheap.

| Parameter | Default | Description |
|---|---|---|
| **Dynamic tariffs** | off | Enables cheap grid charging |
| **Price sensor (€/kWh)** | – | e.g. Tibber or aWATTar price sensor |
| **Cheap threshold (€/kWh)** | 0.10 | Below this price, grid charging is triggered |
| **Max. grid charge/day (kWh)** | 3.0 | Daily cap for grid-charged energy |

---

### Step 7: Wallbox

Controls wallbox charge current based on PV surplus **and/or** cleanly separates the
wallbox consumption from the house load.

#### House / wallbox load split (since v0.3.1)

If you configure a **wallbox power sensor**, Maestro separates the EV charge load from
the house load. EWMA smoothing, PV forecast and the optimizer are then **no longer
distorted by EV charge spikes**. The split is independent of the “Wallbox control”
switch — you can wire up the sensor purely for clean statistics.

| Parameter | Default | Description |
|---|---|---|
| **Wallbox control** | off | Enables current-limiting logic |
| **Wallbox type** | e3dc | `e3dc` = native E3DC wallbox (RSCP service); `generic` = openWB / EVCC / any wallbox via custom services |
| **Wallbox power sensor** | – | Wattage sensor of the wallbox (e.g. `sensor.<device>_wallbox_consumption` or `sensor.openwb_chargepoint_4_ladeleistung`). Auto-detected. |
| **House meter already includes wallbox** | auto | `false` for native E3DC wallbox (separate power meter); `true` for openWB on the grid meter. If on, Maestro subtracts the wallbox value from the house power. |
| **Min. current (A)** | 6 | IEC-61851 minimum |
| **Max. current (A)** | 16 | Maximum allowed charge current |
| **Phases** | 3 | 1 or 3 phases |
| **Min. PV surplus (W)** | 1 400 | Wallbox activates only above this surplus |

**New sensors:** `sensor.e3dc_maestro_wallbox_power` (W), `sensor.e3dc_maestro_total_load_power` (W = house + wallbox), `sensor.e3dc_maestro_wallbox_energy_today` (kWh, Energy-Dashboard compatible).

---

### Step 7b: EVCC integration (OpenWB, evcc.io)

Maestro can monitor an EVCC-compatible wallbox and react accordingly.

| Parameter | Default | Description |
|---|---|---|
| **EVCC integration** | off | |
| **EVCC charging sensor** | – | Sensor or binary sensor showing whether the car is actively charging |
| **EVCC mode sensor** | – | Sensor reporting the active charging mode |
| **Now-mode value** | `now` | Which mode-sensor value counts as "instant charge" (evcc.io: `now`; OpenWB: `Instant Charging`) |
| **Discharge limit in Now mode** | `0` W | Max battery discharge power while EVCC charges in Now mode. `0` = fully block discharge. |

---

### Step 8: Heat pump

Switches the heat pump on when PV surplus is available.

| Parameter | Default | Description |
|---|---|---|
| **HP control** | off | |
| **HP switch entity** | – | `switch.xxx` or `input_boolean.xxx` |
| **Min. PV surplus (W)** | 2 000 | Switch-on threshold |
| **Max. electricity price (€/kWh)** | 0.15 | No switch-on above this price |
| **HP min. run time (min)** | 20 | HP stays on for at least this long |
| **HP min. pause time (min)** | 15 | HP stays off for at least this long |

---

### Step 9: Failsafe & watchdog

| Parameter | Default | Description |
|---|---|---|
| **Watchdog timeout (min)** | 10 | After this many minutes with sensor errors, Maestro sends a persistent HA notification. `0` = disabled. |

---

### Step 10: F0 / Gentle-Charge & F3 Auto-Mode

Fine-tuning of the gentle-charge ramp and the auto-optimiser objective. Defaults
are sensible — advanced tuning only.

---

### Step 11: Battery & PV Sizing Advisor (v0.3.7)

The Sizing Advisor runs a **2D historical simulation** (additional battery
× additional PV) on hourly energy data from the **HA Energy Dashboard** (Recorder
long-term statistics, `statistics_during_period`). It calculates savings, payback
time, self-sufficiency and three recommendations.

> **✨ Auto-detection:** all energy sensors (PV, house, grid import/export,
> battery charge/discharge, optional wallbox + heat pump) are pre-filled from the
> HA Energy Dashboard. The PV slot accepts **multiple sensors** (multi-inverter
> setups). RSCP sensors are used as fallback.

| Parameter | Default | Range | Description |
|---|---:|:---:|---|
| Analysis period | 365 days | 30–730 | How many days of history to analyse |
| Electricity price | 0.30 €/kWh | 0.05–2.00 | For savings calculation |
| Feed-in tariff | 0.08 €/kWh | 0.00–1.00 | FiT revenue for avoided grid export |
| Battery price | 600 €/kWh | 100–5 000 | Battery investment cost |
| PV price | 1 200 €/kWp | 200–5 000 | PV expansion investment cost |
| Inverter upgrade flat | 1 500 € | 0–20 000 | One-off cost for inverter replacement |
| Round-trip efficiency | 92 % | 50–100 % | Battery charge/discharge round-trip |
| Max. battery sweep | 30 kWh | 5–200 | Upper bound for battery sweep |
| Battery step size | 2.5 kWh | 0.5–10 | Resolution along the battery axis |
| Max. PV sweep | 20 kWp | 0–200 | Upper bound for PV sweep |
| PV step size | 2.0 kWp | 0.5–10 | Resolution along the PV axis |

The analysis is started via **Sizing Advisor → Start analysis** in the dashboard
(button entity `button.e3dc_maestro_sizing_analyse_starten`). It runs in a thread
pool (does not block the HA event loop). The result is persisted via `Store` and
survives HA restarts.

> **Scenario sliders:** the scenario explorer (sliders for additional battery /
> PV) interpolates bilinearly inside the sweep matrix, so live updates are
> CPU-free. The cost inputs (battery price, PV price, inverter upgrade, extra)
> recalculate investment and payback **instantly** without re-running the
> simulation.

---

## Provided Entities

All entities appear under the device **E3DC Maestro** in *Settings → Devices & Services → E3DC Maestro → Show device*.

---

### Sensors – Standard (enabled)

| Entity ID | Name | Unit | Description |
|---|---|---|---|
| `sensor.e3dc_maestro_regelphase` | Control phase | – | Current active phase (enum, see rule logic) |
| `sensor.e3dc_maestro_ziel_ladeleistung` | Target charge power | W | Calculated target charge power (0 when inactive) |
| `sensor.e3dc_maestro_ziel_soc` | Target SoC | % | Current daily charge target |
| `sensor.e3dc_maestro_letzte_aktion` | Last action | – | Phase + reason + parameters of the last control action (as attributes) |
| `sensor.e3dc_maestro_geladen_heute` | Charged today | kWh | Energy charged today |
| `sensor.e3dc_maestro_entladen_heute` | Discharged today | kWh | Energy discharged today |
| `sensor.e3dc_maestro_einspeise_eingriffe_heute` | Feed-in interventions today | – | Number of interventions due to feed-in limit |
| `sensor.e3dc_maestro_pv_verlust_verhindert_heute` | PV loss prevented today | kWh | Sum of prevented curtailment + feed-in limit interventions |
| `sensor.e3dc_maestro_autonomiezeit` | Autonomy time | – | Estimated battery range as "Xh YYmin" |
| `sensor.e3dc_maestro_vorausschauendes_ladeziel` | Forward-looking charge target | % | Dynamic charge target based on tomorrow's PV forecast |
| `sensor.e3dc_maestro_morgen_pv_prognose` | Tomorrow PV forecast | kWh | Solcast forecast for tomorrow |
| `sensor.e3dc_maestro_morgen_energiedefizit` | Tomorrow energy deficit | kWh | max(0, consumption − PV) tomorrow |
| `sensor.e3dc_maestro_saisonales_ladeende_uhrzeit` | Seasonal charge end | – | Calculated charge end target today (HH:MM) |
| `sensor.e3dc_maestro_astro_ladestart_uhrzeit` | Astro charge start | – | Calculated charge start after sunrise (HH:MM) |
| `sensor.e3dc_maestro_forecast_min_soc_nachste_24h` | Forecast: Min SoC next 24h | % | Simulated minimum SoC in the next 24 h |
| `sensor.e3dc_maestro_forecast_max_soc_nachste_24h` | Forecast: Max SoC next 24h | % | Simulated maximum SoC |
| `sensor.e3dc_maestro_forecast_netzbezug_nachste_24h` | Forecast: Grid draw next 24h | kWh | Simulated grid import |
| `sensor.e3dc_maestro_forecast_autarkie_nachste_24h` | Forecast: Self-sufficiency next 24h | % | Simulated self-sufficiency rate |
| `sensor.e3dc_maestro_forecast_soc_trajektorie_24h` | Forecast: SoC trajectory 24h | % | ApexCharts sensor with hourly SoC points (attributes) |
| `sensor.e3dc_maestro_forecast_datenqualitat` | Forecast: Data quality | – | Shows whether consumption and PV profiles have sufficient data |
| `sensor.e3dc_maestro_auto_aktive_strategie` | Auto: Active strategy | – | Shows whether auto-optimisation is active and which objective was chosen |
| `sensor.e3dc_maestro_auto_geschatzte_einsparung` | Auto: Estimated savings | % | Simulated improvement vs. baseline |
| `sensor.e3dc_maestro_aktives_lade_limit` | Active charge limit | W | Currently set charge limit (e.g. 0 W when blocked, 3000 W during curtailment guard); `unknown` if no limit active |
| `sensor.e3dc_maestro_aktives_entlade_limit` | Active discharge limit | W | Currently set discharge limit (e.g. 0 W during EVCC pause); `unknown` if no limit active |

#### Sizing Advisor sensors (v0.3.7)

Static analysis results (filled after pressing **Start analysis**):

| Entity ID | Name | Unit | Description |
|---|---|---|---|
| `sensor.e3dc_maestro_advisor_status` | Advisor status | – | `idle` / `running` / `ready` |
| `sensor.e3dc_maestro_advisor_baseline_netzbezug` | Baseline grid import | kWh | Historic actual grid import (baseline scenario) |
| `sensor.e3dc_maestro_advisor_empfehlung_wirtschaftlich` | Recommendation – economic | – | Combination with min. payback time (attributes: full breakdown) |
| `sensor.e3dc_maestro_advisor_empfehlung_technisch` | Recommendation – technical | – | Combination with max. self-sufficiency |
| `sensor.e3dc_maestro_advisor_empfehlung_ausgewogen` | Recommendation – balanced | – | Pareto-knee of cost/benefit curve |
| `sensor.e3dc_maestro_advisor_anomalierate` | Anomaly rate | % | Share of hours with energy-balance anomalies (>5 % house load) |

Scenario sensors (live, follow the two sliders):

| Entity ID | Name | Unit | Description |
|---|---|---|---|
| `sensor.e3dc_maestro_advisor_autarkie` | Scenario self-sufficiency | % | For the current slider values |
| `sensor.e3dc_maestro_advisor_vermiedener_netzbezug` | Avoided grid import (scenario) | kWh | Per year |
| `sensor.e3dc_maestro_advisor_einsparung` | Annual savings (scenario) | EUR | Per year |
| `sensor.e3dc_maestro_advisor_investition` | Investment (scenario) | EUR | Live from price entities |
| `sensor.e3dc_maestro_advisor_amortisationszeit` | Payback time (scenario) | years | Live from price entities |
| `sensor.e3dc_maestro_advisor_zyklen_pro_jahr` | Cycles per year (scenario) | – | Battery wear indicator |

---

### Sensors – Diagnostic (enable manually)

These sensors are **disabled** by default (shown greyed out in the entity list). Enable them manually if needed.

| Entity ID | Name | Description |
|---|---|---|
| `sensor.e3dc_maestro_abregelung_verhindert_heute` | Curtailment prevented today | Energy secured by feed-in limit intervention (detail value of `pv_verlust_verhindert`) |
| `sensor.e3dc_maestro_dc_abregelung_verhindert_heute` | DC curtailment prevented today | Energy secured by curtailment guard (detail value) |
| `sensor.e3dc_maestro_notstromreserve_aktuell` | Emergency reserve (current) | Currently calculated reserve SoC (seasonally interpolated) |
| `sensor.e3dc_maestro_notstromreserve_adaptiv` | Emergency reserve (adaptive) | Consumption-adaptive calculated reserve |
| `sensor.e3dc_maestro_ht_reserve_adaptiv` | HT reserve (adaptive) | Adaptively calculated HT reserve |
| `sensor.e3dc_maestro_debug_log` | Debug log | Last 5 rule log entries; only useful with debug logging enabled |

---

### How to enable disabled entities

1. **Settings → Devices & Services → E3DC Maestro → Show device**
2. Scroll to the entity list, click **"Show disabled entities"** (link at the bottom)
3. Click the desired entity
4. In the dialog: **"Enable entity"** → Confirm
5. The entity will show values after the next update cycle (~30 s)

Alternatively via *Settings → Entities*: filter by "E3DC Maestro" + tick "Show only disabled".

---

### Binary Sensors

| Entity ID | Name | Meaning |
|---|---|---|
| `binary_sensor.e3dc_maestro_e3dc_erreichbar` | E3DC reachable | E3DC responds to RSCP requests |
| `binary_sensor.e3dc_maestro_einspeisedrosselung_aktiv` | Feed-in throttling active | `feed_in_limit` phase active |
| `binary_sensor.e3dc_maestro_ht_schutz_aktiv` | HT protection active | `ht_protection` phase active |
| `binary_sensor.e3dc_maestro_notfallladung_aktiv` | Emergency charging active | `emergency` phase active |
| `binary_sensor.e3dc_maestro_abregelschutz_aktiv` | Curtailment guard active | `curtailment_guard` phase active |
| `binary_sensor.e3dc_maestro_ladesperre_aktiv` | Charge block active | `on` when Maestro has set a charge limit ≤ 0 W |
| `binary_sensor.e3dc_maestro_entladesperre_aktiv` | Discharge block active | `on` when Maestro has set a discharge limit ≤ 0 W (e.g. during EVCC pause) |
| `binary_sensor.e3dc_maestro_advisor_wr_upgrade_empfohlen` | Inverter upgrade recommended (Advisor) | `on` when the current slider scenario **or** the economic recommendation requires an inverter upgrade |

---

### Switches

| Entity ID | Name | Description |
|---|---|---|
| `switch.e3dc_maestro_regelung_aktiv` | Control active | **Master switch** — disables all control interventions |
| `switch.e3dc_maestro_erzwungene_entladung` | Forced discharge | Forces battery discharge, e.g. to free up capacity before a Tibber low-price window |
| `switch.e3dc_maestro_ht_nt_schutz` | HT/NT protection | Peak-tariff protection on/off |
| `switch.e3dc_maestro_ht_samstag` | HT Saturday | HT protection also on Saturdays |
| `switch.e3dc_maestro_ht_sonntag` | HT Sunday | HT protection also on Sundays |
| `switch.e3dc_maestro_wallbox_regelung` | Wallbox control | Wallbox control on/off |
| `switch.e3dc_maestro_warmepumpen_regelung` | Heat pump control | HP control on/off |
| `switch.e3dc_maestro_debug_logging` | Debug logging | Enables verbose log entries in the debug sensor |
| `switch.e3dc_maestro_saisonale_notstromreserve` | Seasonal emergency reserve | Seasonally interpolated reserve on/off |
| `switch.e3dc_maestro_adaptive_reserve_verbrauchsmittel` | Adaptive reserve | Consumption-adaptive reserve on/off |
| `switch.e3dc_maestro_evcc_integration` | EVCC integration | Enables EVCC/OpenWB coupling |
| `switch.e3dc_maestro_abregelschutz` | Curtailment guard | Curtailment guard on/off |
| `switch.e3dc_maestro_korridor_pause_min_ladeleistung` | Corridor pause | Pauses charging when power would fall below the minimum |
| `switch.e3dc_maestro_spat_ladung_two_tier` | Late charging (two-tier) | Second charge target in the evening |
| `switch.e3dc_maestro_vorentladung_tibber_auto` | Pre-discharge Tibber auto | Automatic pre-discharge based on Tibber price |
| `switch.e3dc_maestro_ladeverteilung_spreading` | Charge spreading | Spread PV surplus evenly (default ON since v0.3.1) |
| `switch.e3dc_maestro_astro_modus_sonnenuberwachung` | Astro mode | Link charge end/start to sun position |
| `switch.e3dc_maestro_morning_cap_soc_deckel_morgens` | Morning cap | Morning SoC ceiling active |
| `switch.e3dc_maestro_schonladung_reduzierte_ladeleistung` | Gentle charging | Reduced charge power for battery health |
| `switch.e3dc_maestro_auto_optimierung` | Auto-optimisation | Grid-search optimiser on/off |
| `switch.e3dc_maestro_hard_soc_limit_akku_deckel` | Hard SoC limit | Fixed charge ceiling on/off |
| `switch.e3dc_maestro_vorausschauende_ladung` | Forward-looking charging | Raises today's charge target if tomorrow's PV is expected to be low |

---

### Numbers

All Config Flow parameters are also available as Number entities and can be **changed live** (immediately persisted, no restart required).

| Entity ID | Name | Unit |
|---|---|---|
| `number.e3dc_maestro_wr_leistung` | Inverter power | W |
| `number.e3dc_maestro_max_ladeleistung` | Max. charge power | W |
| `number.e3dc_maestro_min_ladeleistung` | Min. charge power | W |
| `number.e3dc_maestro_installierte_pv_leistung` | Installed PV capacity | kWp |
| `number.e3dc_maestro_einspeisegrenze` | Feed-in limit | % |
| `number.e3dc_maestro_ladeschwelle` | Charge threshold | % |
| `number.e3dc_maestro_ladeende_soc` | Charge target SoC | % |
| `number.e3dc_maestro_ladeende_winter` | Charge end winter | h |
| `number.e3dc_maestro_ladeende_sommer` | Charge end summer | h |
| `number.e3dc_maestro_sommerladeende_ziel` | Summer charge end target | h |
| `number.e3dc_maestro_spreading_ziel_soc` | Spreading target SoC | % |
| `number.e3dc_maestro_unterer_ladekorridor` | Lower charge corridor | W |
| `number.e3dc_maestro_oberer_ladekorridor` | Upper charge corridor | W |
| `number.e3dc_maestro_ht_beginn` | HT start | h |
| `number.e3dc_maestro_ht_ende` | HT end | h |
| `number.e3dc_maestro_ht_reserve_winter` | HT reserve winter | % |
| `number.e3dc_maestro_ht_sockel_aquinoktium` | HT reserve equinox | % |
| `number.e3dc_maestro_gunstig_schwelle` | Cheap threshold | €/kWh |
| `number.e3dc_maestro_max_netzladung_tag` | Max. grid charge/day | kWh |
| `number.e3dc_maestro_wallbox_min_strom` | Wallbox min. current | A |
| `number.e3dc_maestro_wallbox_max_strom` | Wallbox max. current | A |
| `number.e3dc_maestro_wallbox_mindest_uberschuss` | Wallbox min. surplus | W |
| `number.e3dc_maestro_wp_mindest_uberschuss` | HP min. surplus | W |
| `number.e3dc_maestro_wp_max_preis` | HP max. price | €/kWh |
| `number.e3dc_maestro_wp_mindestlaufzeit` | HP min. run time | min |
| `number.e3dc_maestro_wp_mindestpause` | HP min. pause time | min |
| `number.e3dc_maestro_watchdog_timeout` | Watchdog timeout | min |
| `number.e3dc_maestro_ladeleistungs_anlauf` | Charge ramp | W/cycle |
| `number.e3dc_maestro_notstromreserve_winter` | Emergency reserve winter | % |
| `number.e3dc_maestro_notstromreserve_aquinoktium` | Emergency reserve equinox | % |
| `number.e3dc_maestro_abregelschutz_einschaltschwelle` | Curtailment guard activation threshold | W |
| `number.e3dc_maestro_abregelschutz_ausschaltschwelle` | Curtailment guard release threshold | W |
| `number.e3dc_maestro_spatziel_soc` | Late target SoC | % |
| `number.e3dc_maestro_spat_ladeende_stunde` | Late charge end hour | h |
| `number.e3dc_maestro_vorentladungs_ziel_soc` | Pre-discharge target SoC | % |
| `number.e3dc_maestro_vorentladungs_einschwelle_soc` | Pre-discharge activation SoC | % |
| `number.e3dc_maestro_vorentladungs_offset_stunden_vor_ladestart` | Pre-discharge offset | h |
| `number.e3dc_maestro_vorentladungs_max_leistung` | Pre-discharge max. power | W |
| `number.e3dc_maestro_erzwungene_entladungsleistung` | Forced discharge power | W |
| `number.e3dc_maestro_tibber_schwelle_fur_netzexport` | Tibber threshold for grid export | €/kWh |
| `number.e3dc_maestro_ladeende_offset_zu_sonnenuntergang` | Charge end offset to sunset | h |
| `number.e3dc_maestro_ladestart_offset_nach_sonnenaufgang` | Charge start offset after sunrise | h |
| `number.e3dc_maestro_morning_cap_soc_grenze` | Morning cap SoC ceiling | % |
| `number.e3dc_maestro_morning_cap_aktiv_bis_uhr_lokal` | Morning cap active until (hour) | h |
| `number.e3dc_maestro_schonladung_faktor` | Gentle charge factor | – |
| `number.e3dc_maestro_hard_soc_limit_akku_deckel` | Hard SoC limit | % |
| `number.e3dc_maestro_vorausschauende_ladung_max_soc` | Forward-looking charge max SoC | % |

#### Sizing Advisor numbers (v0.3.7)

| Entity ID | Name | Unit |
|---|---|---|
| `number.e3dc_maestro_advisor_hypothetische_batteriekapazitat` | Hypothetical additional battery | kWh |
| `number.e3dc_maestro_advisor_hypothetische_pv_erweiterung` | Hypothetical additional PV | kWp |
| `number.e3dc_maestro_advisor_preis_akku_eur_kwh` | Battery price | €/kWh |
| `number.e3dc_maestro_advisor_preis_pv_eur_kwp` | PV price | €/kWp |
| `number.e3dc_maestro_advisor_preis_wr_upgrade_eur` | Inverter upgrade price | € |
| `number.e3dc_maestro_advisor_zusatzkosten_eur_montage_nebenkosten` | Extra costs (installation, misc.) | € |

---

### Selects

| Entity ID | Name | Options |
|---|---|---|
| `select.e3dc_maestro_wallbox_typ` | Wallbox type | `e3dc`, `generic` |
| `select.e3dc_maestro_vorentladungs_modus` | Pre-discharge mode | `off`, `passive`, `active_house`, `active_grid` |
| `select.e3dc_maestro_auto_optimierung_ziel` | Auto-optimisation objective | `self_consumption`, `cost`, `co2` |

---

### Buttons

| Entity ID | Name | Action |
|---|---|---|
| `button.e3dc_maestro_limits_jetzt_freigeben` | Release limits now | Clears all active power limits (service `clear_power_limits`) |
| `button.e3dc_maestro_manuell_laden_3_kwh` | Manual charge (3 kWh) | Triggers an immediate 3 kWh charge (rate-limited: max. once every 2 h) |
| `button.e3dc_maestro_statistik_zurucksetzen` | Reset statistics | Resets all daily statistics (charged, discharged, PV loss) to 0 |
| `button.e3dc_maestro_sizing_analyse_starten` | Start sizing analysis (v0.3.7) | Triggers the 2D sweep simulation in a background thread pool |

---

## Rule Logic & Phase Priority

Maestro decides **every tick** (default: 30 s) in descending priority. The first matching phase wins.

| Priority | Phase | Trigger | Action |
|---|---|---|---|
| 1 | `off` | Master switch disabled | No interventions |
| 2 | `manual` | Manual charge running | Wait until complete |
| 3 | `emergency` | SoC < charge threshold | Max. charge power |
| 4 | `feed_in_limit` | Export > feed-in limit | Increase charge power |
| 5 | `reserve_protection` | SoC ≤ seasonal emergency reserve | Block discharge |
| 6 | `evcc_pause` | EVCC charging in Now mode | Pause Maestro control |
| 7 | `ht_protection` | HT window + SoC < HT reserve | Block discharge |
| 8 | `force_discharge` | "Forced discharge" switch | Actively discharge |
| 9 | `morning_discharge` | Pre-discharge conditions met | Discharge in morning |
| 10 | `astro_wait` | Before astro charge-start time | Not yet charging |
| 11 | `morning_cap` | SoC > morning cap and before cap hour | Block charging |
| 12 | `hard_soc_limit` | SoC ≥ hard SoC limit | Block charging (1 W sentinel) |
| 13 | `corridor` | SoC < daily target | Seasonal charging |
| 14 | `pv_delay` | Corridor active but PV forecast sufficient | Wait for PV |
| 15 | `spreading` | Corridor active + spreading enabled (default ON) | Distribute charge power over time, smooth charge curve |
| 16 | `curtailment_guard` | Curtailment guard flag active | Hold minimum charge power |
| 17 | `idle` | No action needed | clear_power_limits (E3DC takes over) |

> **Note on `idle`:** In idle state Maestro sends `clear_power_limits`. The E3DC then autonomously routes PV surplus into the battery, even if the target SoC has already been reached. This is intentional.

---

## Import Dashboard

The included dashboard [`dashboards/maestro_dashboard.yaml`](dashboards/maestro_dashboard.yaml) provides **10 tabs** (incl. **Sizing Advisor** since v0.3.7) with a complete overview, controls, diagnostics and what-if analysis.

### Prerequisites

The dashboard requires the following custom cards from HACS:

| Card | Installation |
|---|---|
| [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) | HACS → Frontend |
| [ApexCharts Card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |

### Method A: New dashboard

> **Important:** The dashboard uses hardcoded help-link paths (e.g. `/e3dc-maestro/help-...`). These only work if the dashboard URL slug is exactly `e3dc-maestro`. HA generates the slug automatically from the title — so name the dashboard **E3DC Maestro** and the slug will be set correctly.

1. **Settings → Dashboards → Add dashboard**
2. Enter the title **E3DC Maestro** (this sets the URL slug to `e3dc-maestro`)
3. *Start with an empty page* or *Start with YAML*
4. Three-dot menu of the new dashboard → **Edit in YAML**
5. Paste the entire content of `maestro_dashboard.yaml` → Save

### Method B: Existing dashboard

1. Three-dot menu of the dashboard → **Edit dashboard**
2. Three-dot menu top right → **Raw configuration editor**
3. Replace content with the content of `maestro_dashboard.yaml` → Save

### Variant: Modern dashboard (alternative)

In addition to the classic dashboard, a **second, selectable** variant
[`dashboards/maestro_dashboard_modern.yaml`](dashboards/maestro_dashboard_modern.yaml)
is available with a modern look: live energy flow, mini-graph trends and
standard HA tile/gauge/entities cards. It covers **all functions and all
help pages** of the classic dashboard — the classic file stays unchanged.

**Additional custom cards (HACS → Frontend):**

| Card | Installation |
|---|---|
| [button-card](https://github.com/custom-cards/button-card) | HACS → Frontend |
| [mini-graph-card](https://github.com/kalkih/mini-graph-card) | HACS → Frontend |
| [apexcharts-card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |
| [power-flow-card-plus](https://github.com/flixlix/power-flow-card-plus) | HACS → Frontend |

> The **Übersicht** tab is fully driven by `custom:button-card` with reusable
> JavaScript templates (defined once in the top-level `button_card_templates`
> block of the YAML). It gives the dashboard a state-of-the-art look:
> gradient phase hero, SoC ring, sign-aware power tiles, animated active
> intervention chips and rich money cards.

> **Important:** The modern dashboard uses hardcoded help-link paths
> (e.g. `/e3dc-maestro-modern/help-...`). These only work if the URL slug
> is exactly `e3dc-maestro-modern`. So name the dashboard **E3DC Maestro
> Modern** when importing.

**Before importing**, open `dashboards/maestro_dashboard_modern.yaml`
and adjust the placeholder E3DC raw entity IDs at the top of the file
(`sensor.e3dc_pv_power`, `sensor.e3dc_house_power`,
`sensor.e3dc_grid_power`, `sensor.e3dc_battery_power`,
`sensor.e3dc_soc`) to match your actual E3DC sensors. They are used by
the power-flow card and the live power mini-graph.

Then follow Method A or B above with the modern YAML and title
**E3DC Maestro Modern**.

---

## Sensor Sign Conventions

Maestro requires **consistent signs**. Wrong signs cause incorrect control behaviour.

| Sensor | Positive means | Negative means |
|---|---|---|
| `grid_power_sensor` | Export to grid | Import from grid |
| `battery_power_sensor` | Battery is charging | Battery is discharging |
| `pv_power_sensor` | Generation (always ≥ 0) | – |
| `house_power_sensor` | Consumption (always ≥ 0) | – |

If your sensors report inverted signs:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "E3DC Grid (sign corrected)"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.your_e3dc_grid_sensor') | float(0)) }}"
      - name: "E3DC Battery (sign corrected)"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.your_e3dc_battery_sensor') | float(0)) }}"
```

After creating the template sensors: restart HA and enter the new entity IDs in the Maestro config flow.

---

## Troubleshooting & FAQ

### Integration doesn't appear in the integration list after HACS download

Clear browser cache (Ctrl+Shift+R), then do a full HA restart (not just reload).

### "E3DC not reachable" / binary sensor red

1. Check that `e3dc_rscp` is working: *Settings → Devices & Services → e3dc_rscp*
2. Check that the E3DC is reachable on the network (ping / E3DC app)
3. Check the watchdog timeout value (default 10 min)

### Control phase is always `idle`, even though SoC is below target

Most common causes:
1. **Master switch off**: check `switch.e3dc_maestro_regelung_aktiv`
2. **Wrong sign** on grid or battery sensor (see above)
3. **Hard SoC limit** lower than current SoC: check `number.e3dc_maestro_hard_soc_limit_akku_deckel`

### Battery keeps charging despite `idle` phase

This is **correct**: in `idle` Maestro sends `clear_power_limits` to the E3DC, which then autonomously routes PV surplus into the battery. Maestro intentionally does not stop the battery in idle.

### PV loss prevented shows 0 kWh even though charging occurred

Only active if either `curtailment_guard` or `feed_in_limit` was triggered. Check:
- `switch.e3dc_maestro_abregelschutz` is enabled
- The curtailment guard activation threshold (`number.e3dc_maestro_abregelschutz_einschaltschwelle`) is correctly configured

### Debug log is empty

1. Enable `switch.e3dc_maestro_debug_logging`
2. Manually enable `sensor.e3dc_maestro_debug_log` (disabled by default)

To get detailed `[decide]` log lines (one per control tick, including EWMA-smoothed PV/load values, current phase and reason), also add this to `configuration.yaml` and restart HA:

```yaml
logger:
  logs:
    custom_components.e3dc_maestro: debug
```

The lines look like:

```
[decide] phase=corridor pv=4520W(ewma) house=890W(ewma) grid=-2510W bat=1120W soc=62% reason=Ladekorridor: SoC 62% → Ziel 75%, Leistung 1120W
```

Very useful for diagnosing why a particular phase was active at any given moment.

### Auto-optimisation stays on "data fallback"

The optimiser requires at least **7 days** of consumption history. Check status via `sensor.e3dc_maestro_forecast_datenqualitat`.

---

## Known Compatibility

| System / Software | Status |
|---|---|
| E3DC S10E Pro | ✅ Tested and in production use |
| E3DC S10E | ✅ Tested |
| All other E3DC systems with RSCP support | ✅ Compatible — RSCP tags are identical across models |
| Home Assistant ≥ 2024.1 | ✅ |
| Home Assistant OS (HAOS) | ✅ |
| Home Assistant Container | ✅ |
| Home Assistant Supervised | ✅ |
| Solcast PV Forecast (HACS) | ✅ Recommended for forward-looking charging and PV delay |
| Forecast.Solar (HA built-in) | ✅ Alternative for PV delay |
| Tibber | ✅ For dynamic tariffs and pre-discharge |
| EVCC | ✅ Via wallbox type `generic` |

---

## Acknowledgements

A big thank you to **Eberhard Mayer** for his pioneering work on [E3DC-Control](https://github.com/Eba-M/E3DC-Control) — a C++ program for the Raspberry Pi that implemented the core ideas of E3DC control years ago.

The following concepts from E3DC-Control directly inspired Maestro:

| Concept | Origin in E3DC-Control |
|---|---|
| Seasonal charge corridor | Charge end between `winterminimum` and `sommermaximum` with daily interpolation |
| Charge threshold / emergency charging | `ladeschwelle` — always charge below a minimum SoC |
| Curtailment guard | `einspeiselimit` — raise charge power to stay within export limit |
| HT protection (peak tariff) | `hton/htoff/htmin` — battery reserve for peak-tariff hours, seasonally via cosine function |
| Delayed charging in summer | `sommerladeende` — delay charging to a later hour |
| RSCP as communication protocol | Built on the RSCP sample program published by E3DC |

Maestro brings these ideas into the Home Assistant ecosystem as a native HACS integration with Config Flow, entities, dashboard and significantly extended logic (PV delay, spreading, forward-looking charging, dynamic tariffs and more).

Also a heartfelt thank you to **Torben Nehmer** for the [e3dc_rscp](https://github.com/torbennehmer/hacs-e3dc) Home Assistant integration, which Maestro uses as its complete communication layer. Without this work, Maestro would not be possible.

---

## Changelog

Release history is maintained in [CHANGELOG.md](CHANGELOG.md).

## License

**GNU Affero General Public License v3.0 (AGPL-3.0)** – see [LICENSE](LICENSE)

E3DC Maestro is **free software**: you may use, study, share and modify it under the terms of the AGPL-3.0.

What this means in practice:

- ✅ Private and commercial **use** is permitted.
- ✅ You may **modify** the code and redistribute your version.
- ⚠️ Any **modified version that you distribute** (e.g. as another HACS integration, fork, app, firmware, …) **must also be released under AGPL-3.0** and its **complete source code must be made available**.
- ⚠️ If you run a **modified version as a network/cloud service** (e.g. a SaaS energy optimiser that users interact with over a network), you **must offer the complete source code of that modified version** to those users.
- ⚠️ The original copyright notice and license must be preserved.

The AGPL was chosen explicitly to keep the control engine, optimiser and forecast logic in `custom_components/e3dc_maestro/` **open and community-owned**. Closed-source forks or proprietary cloud rebrands are **not permitted**.

For questions about commercial licensing or use cases that are not compatible with the AGPL, please contact the author via the issue tracker.


---

## Inhaltsverzeichnis

1. [Funktionsübersicht](#funktionsübersicht)
2. [Screenshots](#screenshots)
3. [Voraussetzungen](#voraussetzungen)
4. [Abhängigkeit: e3dc_rscp konfigurieren](#abhängigkeit-e3dc_rscp-konfigurieren)
5. [Installation via HACS](#installation-via-hacs)
6. [Einrichtung (Config Flow)](#einrichtung-config-flow)
7. [Bereitgestellte Entitäten](#bereitgestellte-entitäten)
   - [Sensoren – Standard (aktiviert)](#sensoren--standard-aktiviert)
   - [Sensoren – Diagnose (manuell aktivieren)](#sensoren--diagnose-manuell-aktivieren)
   - [Wie aktiviere ich deaktivierte Entitäten?](#wie-aktiviere-ich-deaktivierte-entitäten)
   - [Binärsensoren](#binärsensoren)
   - [Schalter (Switches)](#schalter-switches)
   - [Zahlenwerte (Numbers)](#zahlenwerte-numbers)
   - [Auswahlen (Selects)](#auswahlen-selects)
   - [Schaltflächen (Buttons)](#schaltflächen-buttons)
7. [Regellogik & Phasenpriorität](#regellogik--phasenpriorität)
8. [Dashboard importieren](#dashboard-importieren)
9. [Sensor-Vorzeichen-Konventionen](#sensor-vorzeichen-konventionen)
10. [Fehlerbehebung & FAQ](#fehlerbehebung--faq)
11. [Bekannte Kompatibilität](#bekannte-kompatibilität)
12. [Danksagung](#danksagung)
13. [Changelog](CHANGELOG.md)
14. [Lizenz](#lizenz)

---

## Funktionsübersicht

| Feature | Beschreibung |
|---|---|
| **Saisonaler Ladekorridor** | Gleitendes Tagesziel und Ladezeit zwischen Sommer und Winter |
| **Einspeiseschutz** | Reaktive Erhöhung der Ladeleistung wenn Einspeisung > 70 % Grenze |
| **Abregelschutz (Curtailment Guard)** | Präventive Mindest-Ladeleistung bei drohender Abregelung |
| **Notstromreserve** | Saisonal interpolierte oder verbrauchsadaptive Reserve |
| **HT/NT-Schutz** | Entladesperre während der Hochtarif-Zeit |
| **PV-Prognose-Verzögerung** | Laden verzögern, wenn Solcast/Forecast.Solar ausreichend PV ankündigt |
| **Vorausschauendes Laden** | Ladeziel für morgen erhöhen wenn wenig PV erwartet wird |
| **Ladeverteilung (Spreading)** | PV-Überschuss gleichmäßig über die verbleibende Ladezeit verteilen – **seit v0.3.1 standardmäßig aktiv** (Hardware-Schutz vor 0/max-Bursts) |
| **Morgen-Vorentladung** | Akku morgens vorentladen um tagsüber mehr PV aufnehmen zu können |
| **Astro-Modus** | Ladeende/Ladestart dynamisch an Sonnenuntergang/Sonnenaufgang koppeln |
| **Morning-Cap** | SoC-Deckel morgens, damit der Akku nicht zu früh voll ist |
| **Hard-SoC-Limit** | Fester Lade-Deckel für Akkuschonung (unabhängig von allen anderen Phasen) |
| **Auto-Optimierung** | Grid-Search-Optimizer wählt täglich die beste Strategie automatisch |
| **24h Forecast-Simulation** | Vorausberechnete SoC-Trajektorie als ApexCharts-Sensor |
| **Dynamische Tarife** | Netzladung bei günstigem Börsenstrompreis (Tibber, aWATTar) |
| **Tarif-Slots** | Feste Zeitfenster mit abweichenden Lade-/Entladeregeln |
| **Wallbox-Regelung** | Strombegrenzung für Fremdwallboxen via EVCC/generisch; bei nativer E3DC-Wallbox nur sinnvoll für phasenübergreifende Koordination |
| **Wärmepumpen-Regelung** | Ein/Aus nach PV-Überschuss mit Mindestlaufzeit und Mindestpause |
| **Erzwungene Entladung** | Dashboard-Schalter für manuelle Entladung, z. B. um vor einem Tibber-Niedrigpreisfenster Kapazität zu schaffen |
| **Regelungs-Cockpit** | Live Command Center mit Hero-Status, KPI-Kacheln, „Aktiv jetzt"-Chips, 24 h Phasenverlauf und „Warum diese Entscheidung?" |
| **Entscheidungs-Erklärung** | Sensor `decision_explanation` mit vollständigem deutschen Erklärungssatz pro Regelphase (alle 17 Phasen) |
| **Battery & PV Sizing Advisor (v0.3.7)** | 2D-Simulation (Zusatz-Akku × Zusatz-PV) auf historischen Stundendaten — berechnet Einsparung, Amortisation, Autarkie und drei Empfehlungen (wirtschaftlich / technisch / ausgewogen) |
| **287 automatisierte Tests** | Control-Engine, Forecast-Simulator, Optimizer und Sizing Advisor vollständig abgedeckt |

---

## Screenshots

### Tab 1 – Dashboard & Echtzeit-Übersicht
![Dashboard Übersicht](Screenshots/01_dashboard_uebersicht.png)

### Tab 2 – Laden & Ladestrategie
![Laden & Ladestrategie](Screenshots/02_laden_ladestrategie.png)

### Tab 3 – Zeitplanung & Astro-Modus
![Zeitplanung & Astro-Modus](Screenshots/03_zeitplanung_astro.png)

### Tab 4 – Netz & Tarif
![Netz & Tarif](Screenshots/04_netz_tarif.png)

### Tab 5 – Flexibilität (Wallbox, Wärmepumpe, Vorentladung)
![Flexibilität Wallbox Wärmepumpe](Screenshots/05_flexibilitaet_wallbox.png)

### Tab 6 – Einstellungen & Systemparameter
![Einstellungen Systemparameter](Screenshots/06_einstellungen_system.png)

### Tab 7 – Diagnose & Debug
![Diagnose & Debug](Screenshots/07_diagnose.png)

### Tab 8 – Hilfe & Glossar
![Hilfe & Glossar](Screenshots/08_hilfe_glossar.png)

### Tab 9 – Auto-Optimierung
![Auto-Optimierung](Screenshots/09_auto_optimierung.png)

### Tab 10 – Battery & PV Sizing Advisor (v0.3.7)

Neuer Tab: 2D historische Simulation, Szenario-Slider (zusätzlicher Akku / PV),
Live-KPIs (Autarkie, vermiedener Netzbezug, Einsparung, Investition, Amortisation),
drei Empfehlungs-Strategien und editierbare Preisfelder.

---

## Voraussetzungen

| Anforderung | Details |
|---|---|
| **Home Assistant** | ≥ 2024.1.0 (empfohlen: ≥ 2024.11) |
| **HACS** | aktuelle Version |
| **[e3dc_rscp](https://github.com/torbennehmer/hacs-e3dc)** | muss installiert, konfiguriert und aktiv sein |
| **E3DC-Gerät** | Alle E3DC-Systeme die von `e3dc_rscp` unterstützt werden (getestet: S10E, S10E Pro) |
| **Solcast / Forecast.Solar** | optional, aber empfohlen für PV-Prognose-Features (Vorausschauendes Laden, PV-Delay) |

> **Wichtig:** E3DC Maestro liest Sensoren aus `e3dc_rscp` und ruft dessen Services auf (`set_power_limits`, `set_power_mode`, `manual_charge`). Ohne eine funktionsfähige und korrekt konfigurierte `e3dc_rscp`-Integration kann Maestro den Speicher **nicht steuern**.

> **⚠️ AI360 muss deaktiviert sein:** Die E3DC-eigene **AI360**-Funktion muss in den E3DC-Geräteeinstellungen deaktiviert werden. AI360 übersteuert externe Ladevorgaben und ignoriert die Regelungen von Maestro — beide Systeme sind nicht gleichzeitig betreibbar. Die Einstellung findet sich im E3DC-Webinterface oder der E3DC-App unter *Einstellungen → Energiemanagement → AI360*.

---

## Abhängigkeit: e3dc_rscp konfigurieren

Bevor du E3DC Maestro einrichtest, muss `e3dc_rscp` **korrekt eingerichtet** sein. Die häufigste Ursache für Fehlfunktionen sind falsche Sensor-Vorzeichen.

### 1. Vorzeichen prüfen

Maestro erwartet diese Vorzeichenkonvention:

| Sensor | Positiv | Negativ |
|---|---|---|
| `grid_power_sensor` | Einspeisung ins Netz | Bezug aus dem Netz |
| `battery_power_sensor` | Akku lädt | Akku entlädt |
| `pv_power_sensor` | immer ≥ 0 | – |
| `house_power_sensor` | immer ≥ 0 | – |

**So prüfst du es:** Öffne *Entwicklerwerkzeuge → Zustände* in HA und beobachte die Werte während PV-Produktion läuft:
- PV-Sensor: Wert muss positiv sein (~z. B. 4000 W mittags)
- Netz-Sensor: Positiv wenn du ins Netz einspeist, negativ wenn du Strom beziehst
- Akku-Sensor: Positiv während Laden, negativ während Entladen

**Wenn die Vorzeichen invertiert sind**, lege einen Template-Sensor an (z. B. in `configuration.yaml`):

```yaml
template:
  - sensor:
      - name: "E3DC Netz korrigiert"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.dein_netz_sensor') | float(0)) }}"
```

Starte HA nach Änderungen neu.

---

## Installation via HACS

### Schritt 1: Repository hinzufügen

1. **HACS öffnen** → Integrationen → Drei-Punkte-Menü (oben rechts) → **Benutzerdefinierte Repositories**
2. URL eingeben: `https://github.com/TommiG1/hacs-e3dc-maestro`
3. Kategorie: **Integration** → **Hinzufügen**

### Schritt 2: Integration herunterladen

1. In der HACS-Integrationsliste nach **E3DC Maestro** suchen
2. **Herunterladen** klicken → Version bestätigen

### Schritt 3: Home Assistant neu starten

Einstellungen → System → **Neu starten** (kein Reload, echter Neustart)

### Schritt 4: Integration einrichten

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Nach **E3DC Maestro** suchen
3. Einrichtungsassistent starten (siehe nächster Abschnitt)

> **Hinweis:** Falls E3DC Maestro in der Suchliste nicht erscheint, lösche den Browser-Cache (Strg+Shift+R) und versuche es erneut.

---

## Einrichtung (Config Flow)

Der Einrichtungsassistent führt durch **11 Schritte**. Alle Parameter können nachträglich jederzeit unter **Einstellungen → Geräte & Dienste → E3DC Maestro → Konfigurieren** geändert werden — ohne Neustart.

> **Seit v0.3.7:** Der Konfigurieren-Dialog öffnet sich mit einem **zentralen
> Navigations-Menü**. Du kannst direkt zu jedem Bereich springen (Quellen, System,
> Saison, Tarif, Wallbox, Wärmepumpe, Sizing Advisor, …), statt dich linear durch
> alle Schritte zu klicken. Nach dem Speichern eines Bereichs landest du wieder
> im Menü und kannst entweder einen weiteren Bereich ändern oder den Dialog über
> **Speichern & Schließen** beenden.

---

### Schritt 1: Quell-Entities

Weist Maestro die Sensor-Entitäten aus `e3dc_rscp` (oder Modbus) zu.

| Feld | Pflicht | Typische Entity-ID | Konvention |
|---|---|---|---|
| **Ladezustand (SoC)** | ✓ | `sensor.<gerätename>_battery_rsoc` | 0–100 % |
| **PV-Leistung** | ✓ | `sensor.<gerätename>_solar_power` | W, ≥ 0 |
| **Zusätzliche Erzeugung** | – | – | W, ≥ 0, wird zu PV addiert (z. B. zweiter WR) |
| **Hausverbrauch** | ✓ | `sensor.<gerätename>_home_power` | W, ≥ 0 |
| **Netzleistung** | ✓ | `sensor.<gerätename>_grid_power` | W, **positiv = Einspeisung** |
| **Batterieleistung** | ✓ | `sensor.<gerätename>_battery_power` | W, **positiv = Laden, negativ = Entladen** |
| **Geladen heute (kWh)** | – | `sensor.<gerätename>_battery_charge_today` | kWh (RSCP-Tageswert, genauer als interne Riemann-Summe) |
| **Entladen heute (kWh)** | – | `sensor.<gerätename>_battery_discharge_today` | kWh (RSCP-Tageswert) |

> **Tipp:** `<gerätename>` ist der Name, den du beim Einrichten von `e3dc_rscp` vergeben hast. Du findest die genauen Entity-IDs unter *Entwicklerwerkzeuge → Zustände* — suche nach `battery_rsoc`, `solar_power`, `grid_power`.

---

### Schritt 2: Systemparameter

Beschreibt die Hardware deines Systems.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **WR-Nennleistung (W)** | 12 000 | Maximale AC-Ausgangsleistung des Wechselrichters |
| **Installierte PV-Leistung (kWp)** | 10.0 | Für Einspeisegrenze und Prognoseberechnung |
| **Max. Ladeleistung (W)** | 3 000 | Obere Grenze für Batterieladebefehle |
| **Min. Ladeleistung (W)** | 300 | Untere Grenze; darunter wird nicht geladen |
| **Einspeisegrenze (%)** | 70 | Prozent der installierten kWp – bei Überschreitung greift `feed_in_limit` |
| **Aktualisierungsintervall (s)** | 30 | Wie oft Maestro entscheidet; kürzere Intervalle erhöhen DB-Last |
| **Erweiterter Ladekorridor** | aus | Wenn aktiv: Ladeleistung direkt in W statt per Powerfaktor |
| **Unterer Korridor (W)** | 500 | Mindest-Ladeleistung im erweiterten Korridor-Modus |
| **Oberer Korridor (W)** | 1 500 | Maximale Ladeleistung im erweiterten Korridor-Modus |
| **Powerfaktor** | 1.5 | Nur relevant wenn *erweiterter Korridor* deaktiviert |
| **Ladeleistungs-Anlauf (W/Zyklus)** | 500 | Rampe: Ladeleistung erhöht sich maximal um diesen Wert pro Zyklus |

**Powerfaktor-Formel** (Standard ohne erweiterten Korridor):
```
Ladeleistung = Powerfaktor × (Ziel-SoC − Ist-SoC) × WR-Leistung / 100
→ anschließend auf [min_charge_power … max_charge_power] begrenzt
```

---

### Schritt 3: Saison & Ladekorridor

Definiert wann und auf welches SoC-Ziel der Akku täglich geladen wird.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **Ladeschwelle (%)** | 15 | SoC-Unterkante für Notfallladung (Phase `emergency`) |
| **Ladeende SoC (%)** | 85 | Tages-Ziel-SoC für den saisonalen Korridor |
| **Winterminimum Ladebeginn (h)** | 11:00 | Frühestens ab dieser Uhrzeit im Winter laden (Ortszeit) |
| **Sommermaximum Ladebeginn (h)** | 14:00 | Spätester Ladebeginn im Sommer (Ortszeit) |
| **Sommerladeende Zielzeit (h)** | 18:30 | Bis zu dieser Uhrzeit soll der Akku im Sommer geladen sein |

Maestro berechnet täglich **gleitend** (basierend auf dem aktuellen Datum) den optimalen Ladekorridor zwischen den Sommer- und Winterwerten.

---

### Schritt 4: HT/NT-Schutz

Verhindert das Entladen des Akkus während teurer Hochtarif-Stunden.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **HT/NT-Schutz aktivieren** | aus | Aktiviert die gesamte HT-Logik |
| **Hochtarif Beginn (h)** | 6 | Ortszeit (MEZ/MESZ automatisch) |
| **Hochtarif Ende (h)** | 21 | Ortszeit |
| **Speicherreserve Winter (%)** | 50 | Mindest-SoC der im HT-Fenster erhalten bleibt (Winter) |
| **Speicherreserve Äquinoktium (%)** | 10 | Mindest-SoC zur Tagundnachtgleiche |
| **HT auch Samstag** | aus | HT-Schutz gilt auch samstags |
| **HT auch Sonntag** | aus | HT-Schutz gilt auch sonntags |

> Alle Zeitangaben werden in **HA-Lokalzeit** ausgewertet. Keine manuelle UTC-Umrechnung nötig.

---

### Schritt 5: PV-Prognose / Ladeverzögerung

Verzögert den Ladestart des Korridors, wenn die heutige PV-Restprognose ausreicht, den Akku noch zu füllen.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **PV-Prognose-Verzögerung** | aus | Aktiviert Phase `pv_delay` |
| **Prognose-Sensor** | – | Entity-ID eines Sensors der die verbleibenden kWh PV heute liefert |
| **Mindest-Prognose (kWh)** | 5.0 | Absolute Schwelle: nur verzögern wenn Forecast ≥ diesem Wert |
| **Nutzbare Batteriekapazität (kWh)** | 10.0 | Wie viel kWh braucht der Akku noch bis Ziel-SoC |
| **Sicherheitsfaktor** | 1.2 | Forecast muss ≥ Bedarf × Faktor sein |
| **Tomorrow PV Sensor** | – | Für vorausschauendes Laden: Prognose für **morgen** (kWh) |
| **Tomorrow Verbrauch Sensor** | – | Für vorausschauendes Laden: Geschätzter Verbrauch morgen (kWh) |

**Empfohlene Prognose-Sensoren (HACS):**
- [Solcast PV Forecast](https://github.com/BJReplay/ha-solcast-solar): `sensor.solcast_pv_forecast_prognose_heute_verbleibend` (heute) / `sensor.solcast_pv_forecast_prognose_morgen` (morgen)
- [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/): `sensor.energy_production_today_remaining`

---

### Schritt 6: Dynamische Tarife & Tarif-Slots

Lädt den Akku aus dem Netz wenn der Börsenstrompreis günstig ist.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **Dynamische Tarife** | aus | Aktiviert günstig-Laden aus Netz |
| **Preis-Sensor (€/kWh)** | – | z. B. Tibber oder aWATTar-Sensor |
| **Günstig-Schwelle (€/kWh)** | 0.10 | Unter diesem Preis wird aus dem Netz geladen |
| **Max. Netzladung/Tag (kWh)** | 3.0 | Tägliches Limit für Netz-Ladungen |

---

### Schritt 7: Wallbox

Steuert die Ladeleistung der Wallbox nach PV-Überschuss.

> **Hinweis zur nativen E3DC-Wallbox:** E3DC-Systeme regeln ihre integrierte Wallbox bereits eigenständig über das interne Energiemanagement — PV-Überschuss wird dabei automatisch zwischen Akku und Wallbox verteilt. Maestro kann über `set_wallbox_charging_current` nur den **maximalen Ladestrom begrenzen**, ersetzt aber nicht das E3DC-eigene Management. Der praktische Mehrwert für die native E3DC-Wallbox ist daher begrenzt.
>
> **Empfehlung:** Die Wallbox-Regelung ist primär sinnvoll für **Fremdwallboxen** (EVCC, generisch), die das E3DC nicht kennen und keine eigene Überschussregelung haben.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **Wallbox-Regelung** | aus | |
| **Wallbox-Typ** | e3dc | `e3dc` = integrierte E3DC-Wallbox (Strombegrenzung); `generic` = EVCC / beliebige Wallbox |
| **Minimalstrom (A)** | 6 | IEC-61851-Minimum |
| **Maximalstrom (A)** | 16 | Maximal erlaubter Ladestrom |
| **Phasenanzahl** | 3 | 1 oder 3 Phasen |
| **Mindest-PV-Überschuss (W)** | 1 400 | Erst ab diesem Überschuss wird die Wallbox aktiviert |

---

### Schritt 7b: EVCC-Integration (OpenWB, evcc.io)

Maestro kann den Ladestatus einer EVCC-kompatiblen Wallbox (OpenWB, evcc.io oder jede andere EVCC-Instanz) beobachten und darauf reagieren.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **EVCC-Integration aktivieren** | aus | |
| **EVCC Lädt-Sensor** | – | Sensor oder Binary Sensor der anzeigt ob das Auto gerade lädt (z. B. `binary_sensor.evcc_charging`) |
| **EVCC Modus-Sensor** | – | Sensor der den aktiven Lademodus meldet (z. B. `sensor.evcc_loadpoint_mode`) |
| **Now-Modus Wert** | `now` | Welcher Wert des Modus-Sensors als „Sofortladen" gilt (evcc.io: `now`; OpenWB: `Instant Charging`) |
| **Entladungslimit im Now-Modus** | `0` W | Maximale Akku-Entladeleistung während EVCC im Now-Modus lädt. `0` = Entladung vollständig sperren; ein positiver Wert (z. B. `500`) erlaubt einen Grundlastbedarf aus dem Akku. Nachträglich per Number-Entity änderbar. |

**Was passiert bei aktivierter EVCC-Integration:**

Wenn EVCC **lädt** und der Modus-Sensor den konfigurierten Now-Modus-Wert hat (z. B. `now`), wechselt Maestro in Phase `evcc_pause`. Maestro pausiert seine eigene Regellogik (kein Ladekorridor, kein HT-Schutz) und **begrenzt zusätzlich die Akku-Entladung** auf den konfigurierten Wert:

- **0 W (Standard):** Die Entladung wird vollständig gesperrt — das Auto zieht keinen Strom aus dem Akku, sondern nur aus PV und Netz.
- **Positiver Wert (z. B. 500 W):** Der Akku darf bis zu diesem Wert entladen werden, um den Grundlastbedarf des Hauses zu decken. Das Auto greift nicht darüber hinaus auf den Akku zu.

Sobald der Ladevorgang endet (Sensor geht auf `false`) oder der Modus wechselt (z. B. auf `pv`), hebt Maestro das Entladungslimit automatisch auf und arbeitet wieder normal.

In allen anderen EVCC-Modi (`pv`, `minpv`, …) läuft Maestro **normal weiter**, weil EVCC in diesen Modi selbst auf PV-Überschuss wartet und kein Regelkonflikt entsteht.

> **Warum das wichtig ist:** Ohne diese Kopplung würden Maestro und EVCC gleichzeitig um verfügbaren Strom konkurrieren — und das Auto könnte den Hausakku leerziehen. Mit dem Entladungslimit behält der Akku seinen Stand, während das Auto schnellstmöglich geladen wird.

---

### Schritt 8: Wärmepumpe

Schaltet die Wärmepumpe ein wenn PV-Überschuss vorhanden ist.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **WP-Regelung** | aus | |
| **WP-Schalter-Entity** | – | `switch.xxx` oder `input_boolean.xxx` |
| **Mindest-PV-Überschuss (W)** | 2 000 | Einschaltschwelle |
| **Max. Strompreis (€/kWh)** | 0.15 | Kein Einschalten über diesem Preis |
| **WP Mindestlaufzeit (min)** | 20 | WP bleibt mindestens so lange an |
| **WP Mindestpause (min)** | 15 | WP bleibt mindestens so lange aus |

---

### Schritt 9: Failsafe & Watchdog

| Parameter | Standard | Erläuterung |
|---|---|---|
| **Watchdog-Timeout (min)** | 10 | Nach so vielen Minuten mit Sensor-Fehlern sendet Maestro eine HA-Persistente Benachrichtigung. `0` = deaktiviert. |

---

### Schritt 10: F0 / Gentle-Charge & F3 Auto-Modus

Feinjustierung der Gentle-Charge-Rampe und des Optimierungsziels der Auto-Optimierung.
Die Defaults sind sinnvoll — nur fortgeschrittenes Tuning nötig.

---

### Schritt 11: Battery & PV Sizing Advisor (v0.3.7)

Der Sizing Advisor führt eine **2D-historische Simulation** durch (zusätzlicher
Akku × zusätzliche PV) auf stündlichen Energie-Daten aus dem **HA Energy
Dashboard** (Recorder Long-Term Statistics, `statistics_during_period`). Berechnet
werden Einsparung, Amortisation, Autarkie und drei Empfehlungen.

> **✨ Auto-Detect:** alle Energie-Sensoren (PV, Haus, Netzbezug/-einspeisung,
> Akku-Laden/-Entladen, optional Wallbox + Wärmepumpe) werden aus dem
> HA-Energie-Dashboard übernommen. Der PV-Slot akzeptiert **mehrere Sensoren**
> (Multi-Inverter-Setups). RSCP-Sensoren dienen als Fallback.

| Parameter | Standard | Bereich | Beschreibung |
|---|---:|:---:|---|
| Analysezeitraum | 365 Tage | 30–730 | Wie viele Tage Verlaufs-Daten genutzt werden |
| Strompreis | 0,30 €/kWh | 0,05–2,00 | Für die Ersparnis-Berechnung |
| Einspeisevergütung | 0,08 €/kWh | 0,00–1,00 | FiT-Einnahmen bei vermiedener Netzeinspeisung |
| Akku-Preis | 600 €/kWh | 100–5 000 | Investitionskosten Akku |
| PV-Preis | 1 200 €/kWp | 200–5 000 | Investitionskosten PV-Erweiterung |
| WR-Upgrade-Pauschale | 1 500 € | 0–20 000 | Einmalkosten WR-Tausch |
| Wirkungsgrad (Round-Trip) | 92 % | 50–100 % | Akku-Lade-/Entladewirkungsgrad |
| Max. Akku-Sweep | 30 kWh | 5–200 | Obergrenze Akku-Sweep |
| Akku-Schrittweite | 2,5 kWh | 0,5–10 | Auflösung Akku-Achse |
| Max. PV-Sweep | 20 kWp | 0–200 | Obergrenze PV-Sweep |
| PV-Schrittweite | 2,0 kWp | 0,5–10 | Auflösung PV-Achse |

Die Analyse wird im Dashboard über **Sizing Advisor → Analyse starten** gestartet
(Button-Entity `button.e3dc_maestro_sizing_analyse_starten`). Sie läuft in einem
Thread-Pool (blockiert den HA-Event-Loop nicht). Das Ergebnis wird via `Store`
persistiert und überlebt HA-Neustarts.

> **Szenario-Slider:** Der Szenario-Explorer (Slider für zusätzlichen Akku /
> PV) interpoliert bilinear in der Sweep-Matrix — Live-Updates verursachen
> keine CPU-Last. Die Preisfelder (Akku-Preis, PV-Preis, WR-Upgrade, Zusatz)
> berechnen Investition und Amortisation **sofort** neu, ohne dass eine neue
> Simulation läuft.

---

## Bereitgestellte Entitäten

Alle Entitäten erscheinen unter dem Gerät **E3DC Maestro** in *Einstellungen → Geräte & Dienste → E3DC Maestro → Gerät anzeigen*.

---

### Sensoren – Standard (aktiviert)

Diese Sensoren sind nach der Installation direkt sichtbar und nutzbar.

| Entity-ID | Name | Einheit | Beschreibung |
|---|---|---|---|
| `sensor.e3dc_maestro_regelphase` | Regelphase | – | Aktuelle Phase (Enum, s. Regellogik) |
| `sensor.e3dc_maestro_ziel_ladeleistung` | Ziel-Ladeleistung | W | Berechnete Soll-Ladeleistung (0 wenn inaktiv) |
| `sensor.e3dc_maestro_ziel_soc` | Ziel-SoC | % | Aktuelles Tages-Ladeziel |
| `sensor.e3dc_maestro_letzte_aktion` | Letzte Aktion | – | Phase + Grund + Parameter der letzten Regelaktion (als Attribute) |
| `sensor.e3dc_maestro_geladen_heute` | Geladen heute | kWh | Geladene Energie heute |
| `sensor.e3dc_maestro_entladen_heute` | Entladen heute | kWh | Entladene Energie heute |
| `sensor.e3dc_maestro_einspeise_eingriffe_heute` | Einspeise-Eingriffe heute | – | Anzahl Eingriffe wegen Einspeisegrenze |
| `sensor.e3dc_maestro_pv_verlust_verhindert_heute` | PV-Verlust verhindert heute | kWh | Summe: verhinderte Abregelung + Einspeiselimit-Eingriffe |
| `sensor.e3dc_maestro_autonomiezeit` | Autonomiezeit | – | Geschätzte Akku-Reichweite als "Xh YYmin" |
| `sensor.e3dc_maestro_vorausschauendes_ladeziel` | Vorausschauendes Ladeziel | % | Dynamisches Ladeziel basierend auf morgiger PV-Prognose |
| `sensor.e3dc_maestro_morgen_pv_prognose` | Morgen PV-Prognose | kWh | Solcast-Prognose für morgen |
| `sensor.e3dc_maestro_morgen_energiedefizit` | Morgen Energiedefizit | kWh | max(0, Verbrauch − PV) morgen |
| `sensor.e3dc_maestro_saisonales_ladeende_uhrzeit` | Saisonales Ladeende | – | Berechnetes Ladeende-Ziel heute (HH:MM) |
| `sensor.e3dc_maestro_astro_ladestart_uhrzeit` | Astro-Ladestart | – | Berechneter Ladestart nach Sonnenaufgang (HH:MM) |
| `sensor.e3dc_maestro_forecast_min_soc_nachste_24h` | Forecast: Min-SoC nächste 24h | % | Simulierter minimaler SoC in den nächsten 24 h |
| `sensor.e3dc_maestro_forecast_max_soc_nachste_24h` | Forecast: Max-SoC nächste 24h | % | Simulierter maximaler SoC |
| `sensor.e3dc_maestro_forecast_netzbezug_nachste_24h` | Forecast: Netzbezug nächste 24h | kWh | Simulierter Netzbezug |
| `sensor.e3dc_maestro_forecast_autarkie_nachste_24h` | Forecast: Autarkie nächste 24h | % | Simulierte Autarkiequote |
| `sensor.e3dc_maestro_forecast_soc_trajektorie_24h` | Forecast: SoC-Trajektorie 24h | % | ApexCharts-Sensor mit stündlichen SoC-Punkten (Attribute) |
| `sensor.e3dc_maestro_forecast_datenqualitat` | Forecast: Datenqualität | – | Zeigt ob Verbrauchs- und PV-Profil ausreichend Daten haben |
| `sensor.e3dc_maestro_auto_aktive_strategie` | Auto: Aktive Strategie | – | Zeigt ob Auto-Optimierung aktiv und welches Ziel gewählt wurde |
| `sensor.e3dc_maestro_auto_geschatzte_einsparung` | Auto: Geschätzte Einsparung | % | Simulierte Verbesserung gegenüber Baseline |
| `sensor.e3dc_maestro_aktives_lade_limit` | Aktives Lade-Limit | W | Aktuell von Maestro gesetztes Ladelimit (z. B. 0 W bei Ladesperre, 3000 W bei Curtailment Guard); `unknown` wenn kein Limit aktiv |
| `sensor.e3dc_maestro_aktives_entlade_limit` | Aktives Entlade-Limit | W | Aktuell von Maestro gesetztes Entladelimit (z. B. 0 W bei EVCC-Pause); `unknown` wenn kein Limit aktiv |

#### Sizing-Advisor-Sensoren (v0.3.7)

Statische Analyseergebnisse (gefüllt nach „Analyse starten“):

| Entity-ID | Name | Einheit | Beschreibung |
|---|---|---|---|
| `sensor.e3dc_maestro_advisor_status` | Advisor-Status | – | `idle` / `running` / `ready` |
| `sensor.e3dc_maestro_advisor_baseline_netzbezug` | Baseline-Netzbezug | kWh | Historischer Ist-Netzbezug (Basis-Szenario) |
| `sensor.e3dc_maestro_advisor_empfehlung_wirtschaftlich` | Empfehlung wirtschaftlich | – | Kombination mit minimaler Amortisationszeit (Details als Attribute) |
| `sensor.e3dc_maestro_advisor_empfehlung_technisch` | Empfehlung technisch | – | Kombination mit maximaler Autarkie |
| `sensor.e3dc_maestro_advisor_empfehlung_ausgewogen` | Empfehlung ausgewogen | – | Pareto-Knie der Kosten/Nutzen-Kurve |
| `sensor.e3dc_maestro_advisor_anomalierate` | Anomalierate | % | Anteil Stunden mit Energiebilanz-Anomalien (>5 % Hauslast) |

Szenario-Sensoren (live, folgen den beiden Slidern):

| Entity-ID | Name | Einheit | Beschreibung |
|---|---|---|---|
| `sensor.e3dc_maestro_advisor_autarkie` | Szenario-Autarkie | % | Für die aktuellen Slider-Werte |
| `sensor.e3dc_maestro_advisor_vermiedener_netzbezug` | Vermiedener Netzbezug (Szenario) | kWh | Pro Jahr |
| `sensor.e3dc_maestro_advisor_einsparung` | Jahreseinsparung (Szenario) | EUR | Pro Jahr |
| `sensor.e3dc_maestro_advisor_investition` | Investition (Szenario) | EUR | Live aus den Preisfeldern |
| `sensor.e3dc_maestro_advisor_amortisationszeit` | Amortisationszeit (Szenario) | Jahre | Live aus den Preisfeldern |
| `sensor.e3dc_maestro_advisor_zyklen_pro_jahr` | Zyklen pro Jahr (Szenario) | – | Verschleiß-Indikator |

---

### Sensoren – Diagnose (manuell aktivieren)

Diese Sensoren sind nach der Installation **deaktiviert** (erscheinen grau in der Entitätenliste). Sie müssen manuell aktiviert werden wenn du sie nutzen möchtest.

| Entity-ID | Name | Beschreibung |
|---|---|---|
| `sensor.e3dc_maestro_abregelung_verhindert_heute` | Abregelung verhindert heute | Energie die durch Einspeiselimit-Eingriff (70%-Regel) gesichert wurde (Detailwert von `pv_verlust_verhindert`) |
| `sensor.e3dc_maestro_dc_abregelung_verhindert_heute` | DC-Abregelung verhindert heute | Energie die durch Curtailment Guard (DC-seitige Überdimensionierung) gesichert wurde (Detailwert von `pv_verlust_verhindert`) |
| `sensor.e3dc_maestro_notstromreserve_aktuell` | Notstromreserve (aktuell) | Aktuell berechneter Reserve-SoC (saisonal interpoliert) |
| `sensor.e3dc_maestro_notstromreserve_adaptiv` | Notstromreserve (adaptiv) | Verbrauchsadaptiv berechnete Reserve |
| `sensor.e3dc_maestro_ht_reserve_adaptiv` | HT-Reserve (adaptiv) | Adaptiv berechnete HT-Reserve |
| `sensor.e3dc_maestro_debug_log` | Debug-Log | Letzte 5 Regel-Logeinträge; nur sinnvoll wenn Debug-Logging eingeschaltet ist |

---

### Wie aktiviere ich deaktivierte Entitäten?

1. **Einstellungen → Geräte & Dienste → E3DC Maestro → Gerät anzeigen**
2. Scrolle zur Entitätenliste, klicke auf **„Deaktivierte Entitäten anzeigen"** (Link unten)
3. Klicke auf die gewünschte Entität
4. Im Dialog: **„Entität aktivieren"** → Bestätigen
5. Die Entität erscheint nach dem nächsten Aktualisierungszyklus (~30 s) mit Werten

Alternativ über *Einstellungen → Entitäten* suchen: Filter auf „E3DC Maestro" + Häkchen bei „Nur deaktivierte anzeigen".

---

### Binärsensoren

| Entity-ID | Name | Bedeutung |
|---|---|---|
| `binary_sensor.e3dc_maestro_e3dc_erreichbar` | E3DC erreichbar | E3DC antwortet auf RSCP-Anfragen |
| `binary_sensor.e3dc_maestro_einspeisedrosselung_aktiv` | Einspeisedrosselung aktiv | Phase `feed_in_limit` aktiv |
| `binary_sensor.e3dc_maestro_ht_schutz_aktiv` | HT-Schutz aktiv | Phase `ht_protection` aktiv |
| `binary_sensor.e3dc_maestro_notfallladung_aktiv` | Notfallladung aktiv | Phase `emergency` aktiv |
| `binary_sensor.e3dc_maestro_abregelschutz_aktiv` | Abregelschutz aktiv | Phase `curtailment_guard` aktiv |
| `binary_sensor.e3dc_maestro_ladesperre_aktiv` | Ladesperre aktiv | `on` wenn Maestro ein Ladelimit ≤ 0 W gesetzt hat (Akku wird nicht geladen) |
| `binary_sensor.e3dc_maestro_entladesperre_aktiv` | Entladesperre aktiv | `on` wenn Maestro ein Entladelimit ≤ 0 W gesetzt hat (z. B. bei EVCC-Pause) |
| `binary_sensor.e3dc_maestro_advisor_wr_upgrade_empfohlen` | WR-Upgrade empfohlen (Advisor) | `on` wenn das aktuelle Slider-Szenario **oder** die wirtschaftliche Empfehlung einen WR-Upgrade erfordert |

---

### Schalter (Switches)

Alle Switches können im Dashboard, in Automationen und über die UI bedient werden.

| Entity-ID | Name | Beschreibung |
|---|---|---|
| `switch.e3dc_maestro_regelung_aktiv` | Regelung aktiv | **Hauptschalter** — deaktiviert alle Regeleingriffe |
| `switch.e3dc_maestro_erzwungene_entladung` | Erzwungene Entladung | Erzwingt Akku-Entladung, z. B. um vor einem Tibber-Niedrigpreisfenster Kapazität zu schaffen |
| `switch.e3dc_maestro_ht_nt_schutz` | HT/NT-Schutz | HT-Schutz ein/aus |
| `switch.e3dc_maestro_ht_samstag` | HT Samstag | HT-Schutz auch samstags |
| `switch.e3dc_maestro_ht_sonntag` | HT Sonntag | HT-Schutz auch sonntags |
| `switch.e3dc_maestro_wallbox_regelung` | Wallbox-Regelung | Wallbox-Steuerung ein/aus |
| `switch.e3dc_maestro_warmepumpen_regelung` | Wärmepumpen-Regelung | WP-Steuerung ein/aus |
| `switch.e3dc_maestro_debug_logging` | Debug-Logging | Aktiviert ausführliche Log-Einträge im Debug-Sensor |
| `switch.e3dc_maestro_saisonale_notstromreserve` | Saisonale Notstromreserve | Saisonal interpolierte Reserve ein/aus |
| `switch.e3dc_maestro_adaptive_reserve_verbrauchsmittel` | Adaptive Reserve | Verbrauchsadaptive Reserve ein/aus |
| `switch.e3dc_maestro_evcc_integration` | EVCC-Integration | Aktiviert die EVCC/OpenWB-Kopplung: Maestro pausiert wenn EVCC im Now-Modus lädt |
| `switch.e3dc_maestro_abregelschutz` | Abregelschutz | Curtailment Guard ein/aus |
| `switch.e3dc_maestro_korridor_pause_min_ladeleistung` | Korridor-Pause | Hält Ladung an wenn Leistung unter Min-Grenze fiele |
| `switch.e3dc_maestro_spat_ladung_two_tier` | Spät-Ladung (Two-Tier) | Zweites Ladeziel am Abend |
| `switch.e3dc_maestro_vorentladung_tibber_auto` | Vorentladung Tibber-Auto | Automatische Vorentladung basierend auf Tibber-Preis |
| `switch.e3dc_maestro_ladeverteilung_spreading` | Ladeverteilung (Spreading) | PV-Überschuss gleichmäßig verteilen (Default ON seit v0.3.1) |
| `switch.e3dc_maestro_astro_modus_sonnenuberwachung` | Astro-Modus | Ladeende/start an Sonne koppeln |
| `switch.e3dc_maestro_morning_cap_soc_deckel_morgens` | Morning-Cap | SoC-Deckel morgens aktiv |
| `switch.e3dc_maestro_schonladung_reduzierte_ladeleistung` | Schonladung | Reduzierte Ladeleistung für Akkuschonung |
| `switch.e3dc_maestro_auto_optimierung` | Auto-Optimierung | Grid-Search-Optimizer ein/aus |
| `switch.e3dc_maestro_hard_soc_limit_akku_deckel` | Hard-SoC-Limit | Fester Lade-Deckel ein/aus |

---

### Zahlenwerte (Numbers)

Alle Parameter des Config Flow sind auch als Number-Entitäten verfügbar und können **live** geändert werden (sofort persistent gespeichert, kein Neustart nötig).

| Entity-ID | Name | Einheit |
|---|---|---|
| `number.e3dc_maestro_wr_leistung` | WR-Leistung | W |
| `number.e3dc_maestro_max_ladeleistung` | Max. Ladeleistung | W |
| `number.e3dc_maestro_min_ladeleistung` | Min. Ladeleistung | W |
| `number.e3dc_maestro_installierte_pv_leistung` | Installierte PV-Leistung | kWp |
| `number.e3dc_maestro_einspeisegrenze` | Einspeisegrenze | % |
| `number.e3dc_maestro_ladeschwelle` | Ladeschwelle | % |
| `number.e3dc_maestro_ladeende_soc` | Ladeende SoC | % |
| `number.e3dc_maestro_ladeende_winter` | Ladeende Winter | h |
| `number.e3dc_maestro_ladeende_sommer` | Ladeende Sommer | h |
| `number.e3dc_maestro_sommerladeende_ziel` | Sommerladeende Ziel | h |
| `number.e3dc_maestro_spreading_ziel_soc` | Spreading-Ziel SoC | % |
| `number.e3dc_maestro_unterer_ladekorridor` | Unterer Ladekorridor | W |
| `number.e3dc_maestro_oberer_ladekorridor` | Oberer Ladekorridor | W |
| `number.e3dc_maestro_ht_beginn` | HT Beginn | h |
| `number.e3dc_maestro_ht_ende` | HT Ende | h |
| `number.e3dc_maestro_ht_reserve_winter` | HT-Reserve Winter | % |
| `number.e3dc_maestro_ht_sockel_aquinoktium` | HT-Sockel Äquinoktium | % |
| `number.e3dc_maestro_gunstig_schwelle` | Günstig-Schwelle | €/kWh |
| `number.e3dc_maestro_max_netzladung_tag` | Max. Netzladung/Tag | kWh |
| `number.e3dc_maestro_wallbox_min_strom` | Wallbox Min-Strom | A |
| `number.e3dc_maestro_wallbox_max_strom` | Wallbox Max-Strom | A |
| `number.e3dc_maestro_wallbox_mindest_uberschuss` | Wallbox Mindest-Überschuss | W |
| `number.e3dc_maestro_wp_mindest_uberschuss` | WP Mindest-Überschuss | W |
| `number.e3dc_maestro_wp_max_preis` | WP Max-Preis | €/kWh |
| `number.e3dc_maestro_wp_mindestlaufzeit` | WP Mindestlaufzeit | min |
| `number.e3dc_maestro_wp_mindestpause` | WP Mindestpause | min |
| `number.e3dc_maestro_watchdog_timeout` | Watchdog-Timeout | min |
| `number.e3dc_maestro_ladeleistungs_anlauf` | Ladeleistungs-Anlauf | W/Zyklus |
| `number.e3dc_maestro_notstromreserve_winter` | Notstromreserve Winter | % |
| `number.e3dc_maestro_notstromreserve_aquinoktium` | Notstromreserve Äquinoktium | % |
| `number.e3dc_maestro_abregelschutz_einschaltschwelle` | Abregelschutz Einschaltschwelle | W |
| `number.e3dc_maestro_abregelschutz_ausschaltschwelle` | Abregelschutz Ausschaltschwelle | W |
| `number.e3dc_maestro_spatziel_soc` | Spätziel SoC | % |
| `number.e3dc_maestro_spat_ladeende_stunde` | Spät-Ladeende (Stunde) | h |
| `number.e3dc_maestro_vorentladungs_ziel_soc` | Vorentladungs-Ziel SoC | % |
| `number.e3dc_maestro_vorentladungs_einschwelle_soc` | Vorentladungs-Einschwelle SoC | % |
| `number.e3dc_maestro_vorentladungs_offset_stunden_vor_ladestart` | Vorentladungs-Offset | h |
| `number.e3dc_maestro_vorentladungs_max_leistung` | Vorentladungs-Max. Leistung | W |
| `number.e3dc_maestro_erzwungene_entladungsleistung` | Erzwungene Entladungsleistung | W |
| `number.e3dc_maestro_tibber_schwelle_fur_netzexport` | Tibber-Schwelle für Netzexport | €/kWh |
| `number.e3dc_maestro_ladeende_offset_zu_sonnenuntergang` | Ladeende Offset zu Sonnenuntergang | h |
| `number.e3dc_maestro_ladestart_offset_nach_sonnenaufgang` | Ladestart Offset nach Sonnenaufgang | h |
| `number.e3dc_maestro_morning_cap_soc_grenze` | Morning-Cap SoC-Grenze | % |
| `number.e3dc_maestro_morning_cap_aktiv_bis_uhr_lokal` | Morning-Cap aktiv bis (Uhr) | h |
| `number.e3dc_maestro_schonladung_faktor` | Schonladung Faktor | – |
| `number.e3dc_maestro_hard_soc_limit_akku_deckel` | Hard-SoC-Limit | % |
| `number.e3dc_maestro_vorausschauende_ladung_max_soc` | Vorausschauende Ladung Max-SoC | % |

#### Sizing-Advisor-Numbers (v0.3.7)

| Entity-ID | Name | Einheit |
|---|---|---|
| `number.e3dc_maestro_advisor_hypothetische_batteriekapazitat` | Hypothetische Zusatz-Batterie | kWh |
| `number.e3dc_maestro_advisor_hypothetische_pv_erweiterung` | Hypothetische PV-Erweiterung | kWp |
| `number.e3dc_maestro_advisor_preis_akku_eur_kwh` | Akku-Preis | €/kWh |
| `number.e3dc_maestro_advisor_preis_pv_eur_kwp` | PV-Preis | €/kWp |
| `number.e3dc_maestro_advisor_preis_wr_upgrade_eur` | WR-Upgrade-Pauschale | € |
| `number.e3dc_maestro_advisor_zusatzkosten_eur_montage_nebenkosten` | Zusatzkosten (Montage, Nebenkosten) | € |

---

### Auswahlen (Selects)

| Entity-ID | Name | Optionen |
|---|---|---|
| `select.e3dc_maestro_wallbox_typ` | Wallbox-Typ | `e3dc`, `generic` |
| `select.e3dc_maestro_vorentladungs_modus` | Vorentladungs-Modus | `off`, `passive`, `active_house`, `active_grid` |
| `select.e3dc_maestro_auto_optimierung_ziel` | Auto-Optimierung: Ziel | `self_consumption`, `cost`, `co2` |

**Vorentladungs-Modi:**
- `off` — Vorentladung deaktiviert
- `passive` — Morgens nur dann entladen wenn Tibber-Preis über Schwelle
- `active_house` — Aktiv entladen bis Ziel-SoC, Energie geht in Hausverbrauch
- `active_grid` — Aktiv entladen und restlichen Überschuss ins Netz

---

### Schaltflächen (Buttons)

| Entity-ID | Name | Aktion |
|---|---|---|
| `button.e3dc_maestro_limits_jetzt_freigeben` | Limits jetzt freigeben | Setzt alle aktiven Leistungslimits zurück (Service `clear_power_limits`) |
| `button.e3dc_maestro_manuell_laden_3_kwh` | Manuell laden (3 kWh) | Löst Sofortladung von 3 kWh aus (Rate-Limited: max. 1× alle 2 h) |
| `button.e3dc_maestro_statistik_zurucksetzen` | Statistik zurücksetzen | Setzt alle Tagesstatistiken (geladen, entladen, PV-Verlust) auf 0 |
| `button.e3dc_maestro_sizing_analyse_starten` | Sizing-Analyse starten (v0.3.7) | Löst die 2D-Sweep-Simulation in einem Hintergrund-Thread-Pool aus |

---

## Regellogik & Phasenpriorität

Maestro entscheidet **jeden Tick** (Standard: 30 s) in absteigender Priorität. Die erste zutreffende Phase gewinnt.

| Prio | Phase | Auslöser | Aktion |
|---|---|---|---|
| 1 | `off` | Hauptschalter deaktiviert | Keine Eingriffe |
| 2 | `manual` | Manuelle Ladung läuft | Warten bis abgeschlossen |
| 3 | `emergency` | SoC < Ladeschwelle | Max. Ladeleistung |
| 4 | `feed_in_limit` | Einspeisung > Einspeisegrenze | Ladeleistung erhöhen |
| 5 | `reserve_protection` | SoC ≤ saisonale Notstromreserve | Entladen blockieren |
| 6 | `evcc_pause` | EVCC lädt im Now-Modus | Maestro-Regelung pausieren |
| 7 | `ht_protection` | HT-Fenster + SoC < HT-Reserve | Entladen blockieren |
| 8 | `force_discharge` | Schalter „Erzwungene Entladung" | Aktiv entladen |
| 9 | `morning_discharge` | Vorentladungs-Bedingungen erfüllt | Morgens entladen |
| 10 | `astro_wait` | Vor Astro-Ladestart-Zeitpunkt | Laden noch nicht starten |
| 11 | `morning_cap` | SoC > Morning-Cap und vor Cap-Uhrzeit | Laden blockieren |
| 12 | `hard_soc_limit` | SoC ≥ Hard-SoC-Limit | Laden blockieren (1 W Sentinel) |
| 13 | `corridor` | SoC < Tagesziel | Saisonal laden |
| 14 | `pv_delay` | Korridor aktiv, aber PV-Prognose ausreichend | Warten auf PV |
| 15 | `spreading` | Korridor aktiv + Spreading ein (Default ON) | Ladeleistung zeitlich verteilen, sanfte Ladekurve |
| 16 | `curtailment_guard` | Abregelschutz-Flag aktiv | Mindest-Ladeleistung halten |
| 17 | `idle` | Kein Handlungsbedarf | clear_power_limits (E3DC übernimmt) |

> **Hinweis zu `idle`:** Im Idle-Zustand sendet Maestro `clear_power_limits`. Der E3DC lädt danach eigenständig PV-Überschuss in den Akku, auch wenn der Ziel-SoC bereits erreicht ist. Das ist beabsichtigt — der Akku wird dabei nicht durch Maestro gestoppt.

---

## Dashboard importieren

Das mitgelieferte Dashboard [`dashboards/maestro_dashboard.yaml`](dashboards/maestro_dashboard.yaml) bietet **10 Tabs** (inkl. **Sizing Advisor** seit v0.3.7) mit vollständiger Übersicht, Steuerung, Diagnose und What-If-Analyse.

### Voraussetzungen

Das Dashboard nutzt folgende Custom Cards aus HACS:

| Card | Installation |
|---|---|
| [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) | HACS → Frontend |
| [ApexCharts Card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |

### Import-Methode A: Neues Dashboard

1. **Einstellungen → Dashboards → Dashboard hinzufügen**
2. *Mit einer leeren Seite beginnen* oder *Mit YAML beginnen*
3. Drei-Punkte-Menü des neuen Dashboards → **In YAML bearbeiten**
4. Gesamten Inhalt von `maestro_dashboard.yaml` einfügen → Speichern

### Import-Methode B: In bestehendes Dashboard

1. Drei-Punkte-Menü des Dashboards → **Dashboard bearbeiten**
2. Drei-Punkte-Menü oben rechts → **Raw-Konfigurationseditor**
3. Inhalt durch den Inhalt von `maestro_dashboard.yaml` ersetzen → Speichern

### Variante: Modernes Dashboard (alternative Version)

Zusätzlich zum klassischen Dashboard steht eine **zweite, wählbare**
Variante [`dashboards/maestro_dashboard_modern.yaml`](dashboards/maestro_dashboard_modern.yaml)
zur Verfügung — mit modernem Look: Live-Energiefluss, mini-graph-Verläufe
und Standard-HA-Karten (tile/gauge/entities). Sie enthält **alle Funktionen
und alle Hilfe-Seiten** des Classic-Dashboards. Die Classic-Datei bleibt
unverändert.

**Zusätzliche Custom Cards (HACS → Frontend):**

| Card | Installation |
|---|---|
| [button-card](https://github.com/custom-cards/button-card) | HACS → Frontend |
| [mini-graph-card](https://github.com/kalkih/mini-graph-card) | HACS → Frontend |
| [apexcharts-card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |
| [power-flow-card-plus](https://github.com/flixlix/power-flow-card-plus) | HACS → Frontend |

> Die **Übersicht** ist vollständig mit `custom:button-card` und
> wiederverwendbaren JavaScript-Templates aufgebaut (definiert im
> Top-Level-Block `button_card_templates` der YAML). Sie liefert einen
> State-of-the-Art-Look: Gradient-Phase-Hero, SoC-Ring,
> vorzeichenabhängige Power-Tiles, animierte aktive Eingriffe und reiche
> €-Karten.

> **Wichtig:** Das moderne Dashboard verwendet fest codierte Hilfe-Link-Pfade
> (z. B. `/e3dc-maestro-modern/help-...`). Diese funktionieren nur, wenn der
> URL-Slug exakt `e3dc-maestro-modern` lautet. Beim Import daher den Titel
> **E3DC Maestro Modern** verwenden.

**Vor dem Import** öffne `dashboards/maestro_dashboard_modern.yaml` und
passe die Platzhalter-Entity-IDs am Datei-Anfang
(`sensor.e3dc_pv_power`, `sensor.e3dc_house_power`,
`sensor.e3dc_grid_power`, `sensor.e3dc_battery_power`,
`sensor.e3dc_soc`) an deine tatsächlichen E3DC-Sensoren an. Sie werden
von der Power-Flow-Karte und der Live-Leistungs-Mini-Graph verwendet.

Anschließend folge Import-Methode A oder B mit dem modernen YAML und
dem Titel **E3DC Maestro Modern**.

### Tab-Übersicht

| Tab | Inhalt |
|---|---|
| Übersicht | SoC-Gauge, Tagesstatistik, PV-Verlust verhindert, Letzte Aktion, Regelphase-Verlauf |
| Lade-Strategie | Alle Ladeparameter, Korridor-Einstellungen, manuelle Ladung |
| Intelligenz | Vorausschauendes Laden, Auto-Optimierung, Abregelschutz, Spreading, Hard-SoC-Limit |
| Tarife & Netz | Dynamische Tarife, Tarif-Slots, Vorentladung |
| Geräte | Wallbox, Wärmepumpe, EVCC |
| Schutz & Limits | Notstromreserve, HT/NT, Hard-SoC, Morning-Cap |
| System | Systemparameter, Watchdog, Intervall |
| Diagnose | 24h Forecast-Trajektorie, Debug-Log, Sensor-Rohdaten |

---

## Sensor-Vorzeichen-Konventionen

Maestro erwartet **konsistente Vorzeichen**. Falsche Vorzeichen führen zu fehlerhafter Regelung.

| Sensor | Positiv bedeutet | Negativ bedeutet |
|---|---|---|
| `grid_power_sensor` | Einspeisung ins Netz | Bezug aus dem Netz |
| `battery_power_sensor` | Akku wird geladen | Akku wird entladen |
| `pv_power_sensor` | Erzeugung (immer ≥ 0) | – |
| `house_power_sensor` | Verbrauch (immer ≥ 0) | – |

Falls deine Sensoren invertierte Vorzeichen liefern:

```yaml
# configuration.yaml
template:
  - sensor:
      - name: "E3DC Netz (Vorzeichen korrigiert)"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.dein_e3dc_netz_sensor') | float(0)) }}"
      - name: "E3DC Akku (Vorzeichen korrigiert)"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: "{{ -(states('sensor.dein_e3dc_akku_sensor') | float(0)) }}"
```

Nach dem Anlegen der Template-Sensoren: HA neu starten und die neuen Entity-IDs im Config Flow von Maestro eintragen.

---

## Fehlerbehebung & FAQ

### Integration erscheint nach HACS-Download nicht in der Integrationsliste

Browser-Cache leeren (Strg+Shift+R), dann HA neu starten (nicht nur Reload).

### „E3DC nicht erreichbar" / Binärsensor rot

1. Prüfe ob `e3dc_rscp` korrekt läuft: *Einstellungen → Geräte & Dienste → e3dc_rscp*
2. Prüfe ob das E3DC auf dem Netzwerk erreichbar ist (Ping / E3DC App)
3. Prüfe den Watchdog-Timeout-Wert (Standard 10 min)

### Regelphase ist immer `idle`, obwohl SoC unter Ziel

Häufigste Ursachen:
1. **Hauptschalter aus**: `switch.e3dc_maestro_regelung_aktiv` prüfen
2. **Falsches Vorzeichen** am Netz- oder Akku-Sensor (s. oben)
3. **Hard-SoC-Limit** kleiner als aktueller SoC: `number.e3dc_maestro_hard_soc_limit_akku_deckel` prüfen

### Akku lädt trotz idle-Phase weiter

Das ist **korrekt**: Im `idle`-Zustand sendet Maestro `clear_power_limits` an den E3DC, der dann eigenständig PV-Überschuss in den Akku leitet. Maestro stoppt den Akku im Idle bewusst nicht.

### PV-Verlust verhindert zeigt 0 kWh, obwohl geladen wurde

Nur aktiv wenn entweder `curtailment_guard` oder `feed_in_limit` aktiv war. Prüfe:
- `switch.e3dc_maestro_abregelschutz` ist eingeschaltet
- Die Abregelschutz-Einschaltschwelle (`number.e3dc_maestro_abregelschutz_einschaltschwelle`) ist korrekt konfiguriert

### Debug-Log ist leer

1. `switch.e3dc_maestro_debug_logging` aktivieren
2. Sensor `sensor.e3dc_maestro_debug_log` manuell aktivieren (ist standardmäßig deaktiviert)

### Auto-Optimierung bleibt auf „Daten-Fallback"

Der Optimizer benötigt mindestens **7 Tage** Verbrauchshistorie. Status prüfen über `sensor.e3dc_maestro_forecast_datenqualitat`.

---

## Bekannte Kompatibilität

| System / Software | Status |
|---|---|
| E3DC S10E Pro | ✅ Getestet und produktiv im Einsatz |
| E3DC S10E | ✅ Getestet |
| Alle weiteren E3DC-Systeme mit RSCP-Unterstützung | ✅ Kompatibel — RSCP-Tags sind systemübergreifend identisch |
| Home Assistant ≥ 2024.1 | ✅ |
| Home Assistant OS (HAOS) | ✅ |
| Home Assistant Container | ✅ |
| Home Assistant Supervised | ✅ |
| Solcast PV Forecast (HACS) | ✅ Empfohlen für Vorausschauendes Laden und PV-Delay |
| Forecast.Solar (HA built-in) | ✅ Alternativ für PV-Delay |
| Tibber | ✅ Für dynamische Tarife und Vorentladung |
| EVCC | ✅ Via Wallbox-Typ `generic` |

---

## Danksagung

Ein herzlicher Dank gilt **Eberhard Mayer** für seine Pionierarbeit mit [E3DC-Control](https://github.com/Eba-M/E3DC-Control) — einem C++-Programm für den Raspberry Pi, das die Grundideen der E3DC-Regelung bereits vor Jahren verwirklicht hat.

Folgende Konzepte aus E3DC-Control haben Maestro direkt inspiriert:

| Konzept | Ursprung in E3DC-Control |
|---|---|
| Saisonaler Ladekorridor | Ladeende zwischen `winterminimum` und `sommermaximum` mit täglicher Interpolation |
| Ladeschwelle / Notfallladung | `ladeschwelle` — unter einem SoC-Minimum wird immer geladen |
| Abregelschutz | `einspeiselimit` — Ladeleistung wird hochgeregelt um Einspeiselimit einzuhalten |
| HT-Schutz (Hochtarif) | `hton/htoff/htmin` — Speicherreserve für Hochtarifzeiten, saisonal über Cosinusfunktion |
| Verzögertes Laden im Sommer | `sommerladeende` — Laden wird auf spätere Stunde verzögert |
| RSCP als Kommunikationsprotokoll | Aufbauend auf dem von E3DC veröffentlichten RSCP-Beispielprogramm |

Maestro überträgt diese Ideen in die Home-Assistant-Welt als native HACS-Integration mit Config Flow, Entitäten, Dashboard und deutlich erweiterter Logik (PV-Delay, Spreading, Vorausschauendes Laden, dynamische Tarife u.v.m.).

Ebenfalls ein herzlicher Dank an **Torben Nehmer** für die [e3dc_rscp](https://github.com/torbennehmer/hacs-e3dc) Home Assistant Integration, auf der Maestro als Kommunikationsschicht vollständig aufbaut. Ohne diese Arbeit wäre Maestro nicht möglich.

---

## Changelog

Die Release-Historie liegt fortlaufend in [CHANGELOG.md](CHANGELOG.md).

## Lizenz


MIT License – siehe [LICENSE](LICENSE)
