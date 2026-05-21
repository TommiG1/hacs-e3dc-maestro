# Example configuration (production) – E3DC Maestro

This document records the **actual production configuration** of the Maestro operator (Tommi), read from Home Assistant on **21 May 2026**. It serves as a reference for users who e.g. only see **200–300 W charge power** or fail to reach full SoC by evening.

> **Note:** Values come from `config/.storage/core.config_entries` (integration options). **Auto-optimisation** runtime overrides may still enable Morning-Cap overnight even when `morning_cap_enabled: false` — see Auto mode section.

**German version:** [beispiel-konfiguration-betrieb.md](beispiel-konfiguration-betrieb.md)

---

## System (plant)

| Parameter | Value |
|-----------|-------|
| Inverter power | 18,000 W |
| Max. charge power | 9,000 W |
| Min. charge power | **50 W** |
| Installed kWp | 19.125 |
| Battery capacity (usable) | 17.5 kWh |
| Feed-in limit | 70 % |
| Update interval | 10 s |

**Sensors (excerpt):** S10 Pro / e3dc_rscp – SoC, PV, house, grid, battery power; Solcast for PV forecast.

---

## Charging behaviour – main differences vs. “slow charging”

| Parameter | This configuration | Typical problem scenario |
|-----------|-------------------|--------------------------|
| **Gentle charging enabled** | **off** (`gentle_charge_enabled: false`) | on, factor 0.45 → ~45 % of target power |
| **Gentle charge factor** | 0.35 (irrelevant while off) | 0.35–0.45 with switch **on** |
| **Advanced corridor** | **on** | off → power-factor mode |
| Lower / upper corridor | **1,500 / 9,000 W** | 500 / 1,500 W |
| **Load spreading** | **on** | on (default) – smooth over the day |
| **Fast-charge floor** | **on**, until **30 %** SoC | off → slower corridor from the start |
| **Morning cap (manual)** | **off** | on + “active until” 10–12 h |
| **Auto-optimisation** | **on**, objective **cost** | off or objective self-consumption |
| Charge-end SoC (daily target) | **100 %** | 85 % |
| Charge threshold (emergency) | **0 %** | 15 % |
| Charge power ramp | 200 W/cycle | higher value = slower ramp |

**Key message:** With **gentle charging disabled**, a **high upper corridor (9 kW)** and **fast-charge floor until 30 %**, charging in the morning and with PV surplus is much more aggressive than with gentle charge × 0.45 and a low corridor.

---

## Season & charge corridor

| Parameter | Value |
|-----------|-------|
| Charge-end SoC | 100 % |
| Winter minimum charge start | 11:00 |
| Summer maximum charge start | 17:00 |
| Summer charge-end (target time) | **18:00** |
| Astro mode | off |
| Two-tier (late charging) | default (not in options → **off**) |

---

## PV forecast & delay

| Parameter | Value |
|-----------|-------|
| PV forecast delay | **on** |
| Forecast sensor (today) | `sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute` |
| Day-2 / tomorrow | Solcast day 3 / tomorrow |
| Minimum forecast | 50 kWh |
| Safety factor | **1.5** |
| **delay_min_soc** (floor under pv_delay) | **30 %** |

Below 30 % SoC, forecast delay does not block charging — the corridor can rebuild the reserve.

---

## Morning cap & gentle charging (F0)

| Parameter | Value |
|-----------|-------|
| Morning cap enabled (manual) | **off** |
| Morning cap SoC (if enabled) | 40 % |
| Morning cap active until (local) | 10:00 |

With **auto mode on**, the optimiser may still enable Morning-Cap overnight (`morning_cap_enabled: true` in the override) — **gentle charging** is deliberately excluded from the search space.

---

## Auto-optimisation (F3)

| Parameter | Value |
|-----------|-------|
| Auto-optimisation | **on** |
| Optimisation objective | **cost** |

The optimiser only varies **Morning-Cap SoC** and **“active until” hour** (search space e.g. cap 20–80 %, until 7–12 h). **Gentle charging** is not adjusted automatically.

---

## Other active features

| Feature | Status |
|---------|--------|
| Curtailment guard | **on** |
| Forward-looking (low PV tomorrow → charge higher today) | **on**, max. 100 % |
| HT/NT protection | off |
| Dynamic tariffs / grid charging | off (fixed tariff) |
| EVCC pause | on (openWB, discharge limit 800 W) |
| Lower-corridor pause | **on** |
| Hard SoC limit | off |
| Seasonal emergency reserve | off |

---

## Full options list (technical)

<details>
<summary>All 121 integration options (JSON-style)</summary>

```
adaptive_reserve_enabled=False
adaptive_reserve_lookback_days=14.0
adaptive_reserve_max_soc=35.0
adaptive_reserve_min_days=7.0
adaptive_reserve_safety_factor=1.3
advanced_corridor=True
astro_enabled=False
auto_mode_enabled=True
auto_mode_objective=cost
battery_capacity_kwh=17.5
charge_ramp_w_per_cycle=200.0
charge_target=100.0
charge_threshold=0.0
curtailment_guard_enabled=True
delay_min_soc=30.0
dynamic_tariff_enabled=False
evcc_enabled=True
fast_charge_floor_enabled=True
fast_charge_floor_soc=30.0
feed_in_limit_percent=70.0
forward_looking_enabled=True
gentle_charge_enabled=False
gentle_charge_factor=0.35
ht_enabled=False
installed_kwp=19.125
inverter_power=18000.0
lower_corridor=1500.0
lower_corridor_pause_enabled=True
max_charge_power=9000.0
min_charge_power=50.0
morning_cap_enabled=False
morning_cap_soc=40.0
morning_cap_until_h=10.0
pv_forecast_enabled=True
pv_forecast_safety_factor=1.5
pv_forecast_threshold_kwh=50.0
spreading_enabled=True
spreading_target_soc=100.0
summer_charge_end=18.0
summer_maximum_hour=17.0
tariff_mode=fixed
winter_minimum_hour=11.0
upper_corridor=9000.0
… (sensors and sizing parameters see HA export)
```

</details>

---

## Tips for users seeing ~250 W and rain from ~4 pm

Compared to this reference — typical levers:

1. **Turn off gentle charging** or set factor to **1.0** (biggest effect when the switch is on).
2. Enable **fast-charge floor** (e.g. 30–40 %) — full PV surplus until the floor.
3. **Advanced corridor** with a high **upper corridor** (e.g. 5–9 kW).
4. **Morning cap:** earlier “active until” (9–10 h) or understand auto mode (can push cap to 12 h).
5. **Load spreading:** turn **off** deliberately if you want more midday battery charging instead of export (less smooth, more power).
6. Do not set **summer charge-end** too late (here 18:00) — after charge-end hour, full PV surplus only applies when SoC is still below the daily target.

---

*Source: Home Assistant config entry `E3DC Maestro` (entry_id `01KQG0NQV3AG77JVHSH9JTEZQ8`), Maestro v0.3.7.*
