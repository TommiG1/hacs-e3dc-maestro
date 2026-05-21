# Beispiel-Konfiguration (Betrieb) – E3DC Maestro

Diese Datei dokumentiert die **tatsächliche Produktiv-Konfiguration** des Maestro-Betreibers (Tommi), ausgelesen aus Home Assistant am **21.05.2026**. Sie dient als Referenz für Nutzer, die z. B. nur **200–300 W Ladeleistung** sehen oder den Akku abends nicht voll bekommen.

> **Hinweis:** Werte stammen aus `config/.storage/core.config_entries` (Integrations-Optionen). Laufzeit-Overrides der **Auto-Optimierung** können Morning-Cap trotz `morning_cap_enabled: false` nachts setzen – siehe Abschnitt Auto-Modus.

---

## System (Anlage)

| Parameter | Wert |
|-----------|------|
| Wechselrichter-Leistung | 18 000 W |
| Max. Ladeleistung | 9 000 W |
| Min. Ladeleistung | **50 W** |
| Installierte kWp | 19,125 |
| Batteriekapazität (nutzbar) | 17,5 kWh |
| Einspeisegrenze | 70 % |
| Update-Intervall | 10 s |

**Sensoren (Auszug):** S10 Pro / e3dc_rscp – SoC, PV, Haus, Netz, Batterieleistung; Solcast für PV-Prognose.

---

## Ladeverhalten – die wichtigsten Unterschiede zu „langsam laden“

| Parameter | Diese Konfiguration | Typisches Problem-Szenario |
|-----------|-------------------|----------------------------|
| **Schonladung aktiv** | **aus** (`gentle_charge_enabled: false`) | an, Faktor 0,45 → ~45 % der Soll-Leistung |
| **Schonladung Faktor** | 0,35 (irrelevant solange aus) | 0,35–0,45 mit Schalter **an** |
| **Erweiterter Ladekorridor** | **an** | aus → Powerfaktor-Modus |
| Unterer / oberer Korridor | **1 500 / 9 000 W** | 500 / 1 500 W |
| **Ladeverteilung (Spreading)** | **an** | an (Standard) – gleicht über den Tag |
| **Schnelllade-Boden** | **an**, bis **30 %** SoC | aus → langsamer Korridor von Anfang an |
| **Morning-Cap (manuell)** | **aus** | an + „aktiv bis“ 10–12 Uhr |
| **Auto-Optimierung** | **an**, Ziel **Kosten** | aus oder Ziel Autarkie |
| Ladeende SoC (Tagesziel) | **100 %** | 85 % |
| Ladeschwelle (Notfall) | **0 %** | 15 % |
| Ladeleistungs-Anlauf | 200 W/Zyklus | höherer Wert = langsamere Rampe |

**Kernbotschaft:** Mit **deaktivierter Schonladung**, **hohem Korridor-Obergrenze (9 kW)** und **Schnelllade-Boden bis 30 %** wird morgens und bei PV-Überschuss deutlich aggressiver geladen als mit Schonladung × 0,45 und niedrigem Korridor.

---

## Saison & Ladekorridor

| Parameter | Wert |
|-----------|------|
| Ladeende SoC | 100 % |
| Winterminimum Ladebeginn | 11:00 |
| Sommermaximum Ladebeginn | 17:00 |
| Sommerladeende (Zielzeit) | **18:00** |
| Astro-Modus | aus |
| Two-Tier (Spätladung) | Standard (nicht in Optionen → **aus**) |

---

## PV-Prognose & Verzögerung

| Parameter | Wert |
|-----------|------|
| PV-Prognose-Verzögerung | **an** |
| Prognose-Sensor (heute) | `sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute` |
| Tag-2 / morgen | Solcast Tag 3 / Morgen |
| Mindest-Prognose | 50 kWh |
| Sicherheitsfaktor | **1,5** |
| **delay_min_soc** (Floor unter pv_delay) | **30 %** |

Unter 30 % SoC blockiert die Prognose-Verzögerung das Laden nicht – der Korridor darf die Reserve aufbauen.

---

## Morning-Cap & Schonladung (F0)

| Parameter | Wert |
|-----------|------|
| Morning-Cap aktiv (manuell) | **aus** |
| Morning-Cap SoC (falls an) | 40 % |
| Morning-Cap aktiv bis (lokal) | 10:00 |

Bei **Auto-Modus an** kann der Optimizer Morning-Cap nachts trotzdem aktivieren (`morning_cap_enabled: true` im Override) – nur **Schonladung** bleibt bewusst außerhalb des Suchraums.

---

## Auto-Optimierung (F3)

| Parameter | Wert |
|-----------|------|
| Auto-Optimierung | **an** |
| Optimierungsziel | **cost** (Kosten) |

Der Optimizer variiert nur **Morning-Cap SoC** und **„aktiv bis“-Uhrzeit** (Suchraum z. B. Cap 20–80 %, bis 7–12 Uhr). **Schonladung** wird nicht automatisch angepasst.

---

## Weitere aktive Features

| Feature | Status |
|---------|--------|
| Abregelschutz (Curtailment Guard) | **an** |
| Forward-Looking (morgen wenig PV → heute höher laden) | **an**, max. 100 % |
| HT/NT-Schutz | aus |
| Dynamische Tarife / Netzladung | aus (fester Tarif) |
| EVCC-Pause | an (openWB, Entladungslimit 800 W) |
| Unterer-Korridor-Pause | **an** |
| Hard-SoC-Limit | aus |
| Saisonale Notreserve | aus |

---

## Vollständige Options-Liste (technisch)

<details>
<summary>Alle 121 Integrations-Optionen (JSON-artig)</summary>

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
… (Sensoren und Sizing-Parameter siehe HA-Export)
```

</details>

---

## Empfehlung für Nutzer mit ~250 W und Regen ab ~16 Uhr

Vergleich mit dieser Referenz – typische Hebel:

1. **Schonladung ausschalten** oder Faktor **1,0** (größter Effekt bei aktivem Schalter).
2. **Schnelllade-Boden** aktivieren (z. B. 30–40 %) – voller PV-Überschuss bis zum Floor.
3. **Erweiterter Ladekorridor** mit hohem **oberen Korridor** (z. B. 5–9 kW).
4. **Morning-Cap:** früheres „aktiv bis“ (9–10 h) oder Auto-Modus verstehen (kann Cap bis 12 h schieben).
5. **Ladeverteilung:** bewusst **aus** schalten, wenn mittags mehr in den Akku statt ins Netz soll (weniger „glatt“, mehr Leistung).
6. **Sommerladeende** nicht zu spät (hier 18:00) – nach Ladeende-Stunde greift voller PV-Überschuss nur noch, wenn SoC unter Tagesziel.

---

*Quelle: Home Assistant Config Entry `E3DC Maestro` (entry_id `01KQG0NQV3AG77JVHSH9JTEZQ8`), Maestro v0.3.7.*
