# E3DC Maestro v0.3.7 – Battery & PV Sizing Advisor

**Release-Typ:** Major Feature-Release  
**Datum:** 14.05.2026

---

## Übersicht

v0.3.7 führt den **Battery & PV Sizing Advisor** ein – ein vollständiges
Analyse-Werkzeug, das auf Basis der eigenen historischen Messdaten errechnet,
wie viel Geld eine zusätzliche Batteriekapazität und/oder eine PV-Erweiterung
konkret einsparen würde, und welche Kombination sich am schnellsten amortisiert.

Zusätzlich wurde das **Einstellungs-Menü der Integration** komplett neu
strukturiert: statt sich linear durch 14 Schritte klicken zu müssen, gibt es
jetzt ein zentrales Navigations-Menü, von dem aus jeder Bereich direkt
angesteuert werden kann.

---

## 🧭 Neues Navigations-Menü im Options-Flow

Bisher: Wer im Optionen-Dialog (Einstellungen → Integrationen → E3DC Maestro →
Konfigurieren) z. B. nur den Sizing Advisor anpassen wollte, musste sich erst
durch **13 vorgeschaltete Schritte** klicken (Quellen, System, Saison,
PV-Prognose, HT/NT, Tarif-Slots, Tarif, Wallbox, EVCC, Wärmepumpe, Failsafe,
F0/Gentle, F3 Auto-Modus) bevor er ans Ziel kam.

Jetzt: Direkt nach dem Öffnen der Optionen erscheint ein **Menü mit allen 14
Bereichen** als anklickbare Einträge. Nach dem Speichern eines Bereichs kehrt
man automatisch ins Menü zurück und kann den nächsten Bereich bearbeiten – oder
über **„Speichern & Schließen"** den Dialog beenden.

**Menü-Einträge:**

- Quellen-Sensoren
- System-Parameter
- Saison & Korridor
- PV-Prognose / Charge-Delay
- HT/NT Lastspitzen
- Tarif-Zeitfenster
- Dynamischer Tarif
- Wallbox
- EVCC
- Wärmepumpe
- Failsafe
- F0 / Gentle-Charge
- F3 Auto-Modus
- Sizing Advisor
- **Speichern & Schließen**

Die initiale Einrichtung (Config-Flow beim Hinzufügen der Integration) bleibt
weiterhin linear, damit Pflichtfelder nicht übersprungen werden können.

---

## ✨ Neu: Battery & PV Sizing Advisor

### Neues Python-Modul `battery_sizing.py` (902 Zeilen)

Herzstück des Advisors ist ein komplett neues Simulationsmodul, das den gesamten
Berechnungspfad von der Datenbeschaffung bis zur Empfehlung abdeckt.

#### Datenbasis: HA Recorder Long-Term Statistics

Der `SizingDataLoader` liest die stündlichen Energieflüsse der letzten
*N* Tage direkt aus dem HA-Recorder (`statistics_during_period`, `period="hour"`).
Folgende Sensoren werden ausgewertet:

| Sensor-Slot | Pflicht? | Beschreibung |
|---|:---:|---|
| PV-Energie | ✅ | Erzeugte PV-Energie (kWh, total_increasing) |
| Hausverbrauch | ✅ | Gesamter Hausverbrauch inkl. Akku-Lade |
| Netzbezug | ✅ | Aus dem Netz bezogene Energie |
| Netzeinspeisung | ✅ | Ins Netz eingespeiste Energie |
| Akku-Ladung | ✅ | Vom System in den Akku geladene Energie |
| Akku-Entladung | ✅ | Aus dem Akku entnommene Energie |
| Wallbox | ➖ | Optional – Ladestrom E-Auto |
| Wärmepumpe | ➖ | Optional – WP-Verbrauch |

Jeder Stunden-Datensatz wird auf **Energiebilanz-Anomalien** geprüft
(Abweichung > 5 % des Hausverbrauchs). Der Anteil anomaler Stunden wird als
`anomaly_rate` im Ergebnis mitgeführt.

#### Simulationsalgorithmus: stündliche 2D-Replay-Simulation

Für jede Kombination `(zusätzliche Batteriekapazität, zusätzliche PV-Leistung)`
wird eine **vollständige stündliche Replay-Simulation** über alle historischen
Datensätze durchgeführt (`simulate_scenario`).

**Virtueller Zusatz-Akku** (parallel zum realen Bestandssystem):
- Lädt sich aus Überschuss (Netzeinspeisung + zusätzliche PV)
- Entlädt bei Netzbezug
- C-Rate-Limit: **0,5 C** (max. 50 % der Kapazität pro Stunde)
- Round-Trip-Wirkungsgrad: √η je Richtung (Standard: 92 %)

**PV-Erweiterung** wird durch proportionale Skalierung der gemessenen
PV-Erzeugung modelliert (`pv_scale = total_kwp / installed_kwp`), anschließend
durch die **WR-Leistungsgrenze** gecappt (Clipping-Verluste werden separat
erfasst).

**Einspeise-Limit (FiT):** Das Netz-Export-Cap (`feed_in_limit_pct`) wird
auf das erweiterte System angewendet – überschüssige Energie wird zuerst im
Zusatz-Akku zwischengespeichert, Rest wird curtailed.

**WR-Upgrade-Erkennung:**
```
WR-Upgrade nötig wenn:
  (installed_kwp + additional_kwp) > inverter_kw × 1.2
```

Bei WR-Upgrade wird die effektive WR-Grenze auf `total_kwp` angehoben
(neuer, größerer WR).

**Berechnete Kennzahlen je Szenario:**
- `avoided_grid_import_kwh` – vermiedener Netzbezug pro Jahr
- `added_self_consumption_kwh` – zusätzliche Eigennutzung PV
- `reduced_feed_in_kwh` / `inverter_clipping_loss_kwh` – Einspeisung / Clipping
- `self_sufficiency_pct` – Autarkie-Grad (%)
- `cycles_per_year` – Akku-Vollzyklen pro Jahr
- `savings_eur_per_year` – Einsparung (vermiedener Bezug × Strompreis + zusätzl.
  Einspeisung × FiT-Preis)
- `investment_eur` – Investitionssumme inkl. optionalem WR-Upgrade
- `payback_years` – Amortisationszeit (math.inf wenn nicht rentabel)
- `monthly_avoided_kwh[12]` – monatliche Aufschlüsselung Jan–Dez

#### 2D-Sweep-Matrix (`sweep_2d`)

```
Akku-Sweep:  0 … max_battery_kwh  in Schritten von battery_step_kwh
PV-Sweep:    0 … max_pv_kwp       in Schritten von pv_step_kwp
```

Standard-Auflösung: 2,5 kWh-Schritte, 2,0 kWp-Schritte.  
Die Matrix läuft im Thread-Pool (`async_add_executor_job`), um den HA
Event-Loop nicht zu blockieren.

#### Drei Empfehlungs-Strategien

| Strategie | Kriterium |
|---|---|
| **Wirtschaftlich** | Minimale `payback_years` (schnellste Amortisation) |
| **Technisch** | Maximale `self_sufficiency_pct` (höchste Autarkie), Tie-Break: geringste Investition |
| **Ausgewogen** | Pareto-Knie der (Investition, Einsparung)-Kurve – bestes Verhältnis Kosten/Nutzen |

Das Pareto-Knie wird über normierte (0–1) Investitions- und Einsparvektoren
berechnet, der Punkt mit dem größten senkrechten Abstand zur Verbindungsgerade
[min-Investition, max-Investition] wird gewählt.

#### Interpolation für Slider-Szenario (`interpolate_result`)

Statt jeden Slider-Wert neu zu simulieren, wird aus der Matrix **bilinear
interpoliert**. Das erlaubt flüssige Echtzeit-Updates ohne CPU-Last.

#### Persistenz

Das Analyse-Ergebnis wird als JSON in der HA-Storage (`.storage/`) abgelegt
(`Store(version=1, key="e3dc_maestro_sizing_<entry_id>")`). Die Ergebnisse
überleben HA-Neustarts ohne erneuten Analyse-Lauf.

---

### Neue Entities

#### Button
| Entity | Funktion |
|---|---|
| `button.e3dc_maestro_sizing_analyse_starten` | Startet die 2D-Sweep-Simulation (läuft im Hintergrund) |

#### Number (Slider)
| Entity | Bereich | Default | Beschreibung |
|---|:---:|---:|---|
| `number.e3dc_maestro_advisor_hypothetische_batteriekapazitat` | 0–100 kWh | 10 kWh | Szenario-Slider: zusätzliche Akku-Kapazität |
| `number.e3dc_maestro_advisor_hypothetische_pv_erweiterung` | 0–100 kWp | 5 kWp | Szenario-Slider: zusätzliche PV-Leistung |

#### Number (Preisfelder, BOX-Modus)
Alle vier Preisfelder verwenden `NumberMode.BOX` (keine Slider-Optik) und
erlauben freie Eingabe ohne feste Unter-/Obergrenze. Investition und Amortisation
rechnen bei jeder Änderung **sofort** neu – ohne erneuten Analyse-Lauf.

| Entity | Default | Beschreibung |
|---|---:|---|
| `number.e3dc_maestro_advisor_preis_akku_eur_kwh` | 600 €/kWh | Investitionskosten Batteriekapazität |
| `number.e3dc_maestro_advisor_preis_pv_eur_kwp` | 1 200 €/kWp | Investitionskosten PV-Erweiterung |
| `number.e3dc_maestro_advisor_preis_wr_upgrade_eur` | 1 500 € | Pauschale WR-Upgrade |
| `number.e3dc_maestro_advisor_zusatzkosten_eur_montage_nebenkosten` | 0 € | Montage, Nebenkosten, Sonstiges |

Initialwerte werden beim Start aus den Integration-Optionen übernommen; spätere
Änderungen im Dashboard überschreiben sie, bis HA neu gestartet wird.

#### Sensor (statische Analyse-Ergebnisse, `MaestroSizingSensor`)
| Entity | Einheit | Beschreibung |
|---|:---:|---|
| `sensor.e3dc_maestro_advisor_status` | – | Zustand: `idle` / `running` / `ready` |
| `sensor.e3dc_maestro_advisor_baseline_netzbezug` | kWh | Historischer Ist-Netzbezug (Basis-Szenario) |
| `sensor.e3dc_maestro_advisor_empfehlung_wirtschaftlich` | – | Empfohlene Kombination (min. Amortisation) mit Attributen |
| `sensor.e3dc_maestro_advisor_empfehlung_technisch` | – | Empfohlene Kombination (max. Autarkie) mit Attributen |
| `sensor.e3dc_maestro_advisor_empfehlung_ausgewogen` | – | Pareto-Knie-Empfehlung mit Attributen |
| `sensor.e3dc_maestro_advisor_anomalierate` | % | Anteil anomaler Stunden in der Datenbasis |

#### Sensor (Slider-Szenario, `MaestroSizingScenarioSensor`)
| Entity | Einheit | Beschreibung |
|---|:---:|---|
| `sensor.e3dc_maestro_advisor_autarkie` | % | Autarkie-Grad für aktuelles Slider-Szenario |
| `sensor.e3dc_maestro_advisor_vermiedener_netzbezug` | kWh | Vermiedener Netzbezug pro Jahr |
| `sensor.e3dc_maestro_advisor_einsparung` | €/Jahr | Jährliche Geldersparnis |
| `sensor.e3dc_maestro_advisor_investition` | € | Investitionssumme (live aus Preisfeldern) |
| `sensor.e3dc_maestro_advisor_amortisationszeit` | Jahre | Amortisationszeit (live aus Preisfeldern) |
| `sensor.e3dc_maestro_advisor_zyklen_pro_jahr` | – | Akkuvollzyklen pro Jahr (Verschleiß-Indikator) |

Der Szenario-Sensor enthält im Attribut `scenario_investment_breakdown` die
vollständige Investitionsaufschlüsselung:
```json
{
  "battery_eur": 6000,
  "pv_eur": 4800,
  "inverter_eur": 1500,
  "extra_eur": 0,
  "inverter_upgrade_needed": true
}
```

#### Binary Sensor
| Entity | Beschreibung |
|---|---|
| `binary_sensor.e3dc_maestro_advisor_wr_upgrade_empfohlen` | `on` wenn das aktuelle Slider-Szenario **oder** die wirtschaftliche Empfehlung einen WR-Upgrade erfordert |

Der Sensor wird bei jeder Slider-Bewegung live aktualisiert (kein Re-Analyse-Lauf
nötig), da `sizing_scenario_wr_upgrade` als `@property` im Coordinator berechnet
wird.

---

### Neuer Konfigurations-Schritt: Sizing Advisor

Im HA-Konfigurations-Flow (Einstellungen → Integrationen → E3DC Maestro →
Konfigurieren) gibt es einen neuen Schritt **„Sizing Advisor"** mit Auto-Detection
der Energie-Sensoren aus der HA-Energy-Integration sowie folgenden Parametern:

| Parameter | Standard | Bereich | Beschreibung |
|---|---:|:---:|---|
| Analysezeitraum | 365 Tage | 30–730 | Wie viele Tage Verlaufs-Daten genutzt werden |
| Strompreis | 0,30 €/kWh | 0,05–2,00 | Für Ersparnis-Berechnung |
| Einspeisevergütung | 0,08 €/kWh | 0,00–1,00 | FiT-Einnahmen bei vermiedener Netzeinspeisung |
| Akku-Preis | 600 €/kWh | 100–5 000 | Investitionskosten Akku |
| PV-Preis | 1 200 €/kWp | 200–5 000 | Investitionskosten PV-Erweiterung |
| WR-Upgrade-Pauschale | 1 500 € | 0–20 000 | Einmalkosten WR-Tausch |
| Wirkungsgrad (Round-Trip) | 92 % | 50–100 % | Akku-Lade-/Entladewirkungsgrad |
| Max. Akku-Sweep | 30 kWh | 5–200 | Obere Grenze Akku-Sweep |
| Akku-Schrittweite | 2,5 kWh | 0,5–10 | Auflösung Akku-Dimension |
| Max. PV-Sweep | 20 kWp | 0–200 | Obere Grenze PV-Sweep |
| PV-Schrittweite | 2,0 kWp | 0,5–10 | Auflösung PV-Dimension |

---

### Dashboard: Neuer Tab „Sizing Advisor"

Der bestehende `maestro_dashboard.yaml` wurde um einen vollständigen Tab erweitert:

#### Analyse starten
- Button-Karte → triggert `button.e3dc_maestro_sizing_analyse_starten`
- Fortschritts-Indikator via `sensor.e3dc_maestro_advisor_status`
- Hilfe-Button navigiert zur neuen Subview `help-sizing-advisor`

#### Szenario-Explorer (Sliders)
- Slider für hypothetische Batteriekapazität (0–100 kWh)
- Slider für hypothetische PV-Erweiterung (0–100 kWp)
- Bedingte WR-Upgrade-Warnkarte (`binary_sensor ... state: "on"`),
  `multiline_secondary: true` für langen Erklärungstext

#### Live-KPIs
Vier Kennzahl-Karten: Autarkie, Netzbezug, Jahreseinsparung, Investition/Amortisation

#### Drei Empfehlungs-Karten
Grid-Layout (`columns: 3`, `square: false`) mit kompakten Markdown-Tabellen
(Wirtschaftlich / Technisch / Ausgewogen)

#### Investitionskosten (editierbar)
Eine einzelne, volle Breite `entities`-Karte mit allen vier Preisfeldern untereinander.

#### Hilfe-Subview `help-sizing-advisor`
Neue Unterseite mit ausführlicher Erklärung zu Methodik, Parametern, Grenzen
und häufigen Fragen zum Advisor.

---

## 🐛 Behobene Probleme

### Sweep-Matrix: Plateau bei Werten über bisherigem Maximum

**Symptom:** Autarkie und vermiedener Netzbezug stiegen nur bis ~20 kWp / ~30 kWh,
darüber änderte sich nichts mehr.

**Ursache:** Die persistierte Sweep-Matrix war noch mit alten Sweep-Grenzen
berechnet worden. Die bilineare Interpolation clampt Slider-Werte außerhalb des
Matrix-Bereichs auf den Randwert, wodurch alle höheren Szenarien dasselbe Ergebnis
lieferten wie das Randfeld.

**Fix:** Sweep-Grenzen in den Integration-Optionen erhöhen (empfohlen: 100 kWh /
25–50 kWp) und einmalig „Analyse starten" drücken. Die neu berechnete Matrix deckt
dann den vollen Slider-Bereich ab.

---

## 📊 Dashboard-Änderungen (Zusammenfassung)

| Bereich | Änderung |
|---|---|
| Sizing Advisor Tab | Komplett neu – Slider, Live-KPIs, Empfehlungen, Preisfelder |
| Empfehlungs-Karten | `horizontal-stack` → `grid columns: 3` (kein Zeilenumbruch) |
| Investitionskosten | Alle 4 Felder in einer einzigen, volle-Breite-Karte untereinander |
| WR-Upgrade-Warnung | Reaktiv auf Slider-Bewegung, `multiline_secondary: true` |
| Hilfe-Subview | Neue Seite `help-sizing-advisor` mit vollständiger Doku |

---

## ⚙️ Geänderte Dateien

| Datei | Änderungen |
|---|---|
| `battery_sizing.py` | **Neu** – 902 Zeilen: Datenlader, Simulator, Sweep, Empfehlungs-Engine, Interpolation |
| `const.py` | +43 Zeilen: 22 neue `CONF_SIZING_*` Keys + Defaults + Simulations-Konstanten |
| `config_flow.py` | +184 Zeilen: neuer Schritt `sizing_advisor` mit Auto-Detection + vollem Schema |
| `coordinator.py` | +227 Zeilen: `async_run_sizing_analysis()`, Persistenz (`Store`), Slider-Attribute, Preisfelder, `sizing_scenario_wr_upgrade` als `@property` |
| `sensor.py` | +372 Zeilen: `MaestroSizingSensor`, `MaestroSizingScenarioSensor`, Live-Investment-Helper |
| `number.py` | +125 Zeilen: 2 Slider + 4 BOX-Preisfelder, `MaestroSizingNumber` |
| `binary_sensor.py` | +27 Zeilen: `sizing_inverter_upgrade_needed` mit Slider- + Matrix-Prüfung |
| `button.py` | +17 Zeilen: `MaestroRunSizingButton` |
| `strings.json` / `translations/de.json` | +218/+226 Zeilen: alle neuen Entities lokalisiert + neuer `init`-Menü-Step (Options-Flow Navigation) |
| `config_flow.py` (Options-Flow) | Umstellung auf `async_show_menu`: zentrales Navigations-Menü statt linearem Durchklicken, neuer `finish`-Step zum Speichern & Schließen |
| `dashboards/maestro_dashboard.yaml` | +354 Zeilen: neuer Sizing Advisor Tab + Hilfe-Subview |
| `tests/conftest.py` | Minor: Test-Fixtures für Sizing-Tests |
| `tests/test_battery_sizing.py` | **Neu** – Unit-Tests für Simulator und Sweep-Engine |
