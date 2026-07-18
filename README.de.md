[🇬🇧 English](README.md) | 🇩🇪 Deutsch

# E3DC Maestro

Eine Home Assistant Custom Integration für die **intelligente, vollautomatische Lade- und Entladeregelung** von E3DC Heimspeichersystemen.

E3DC Maestro läuft vollständig **lokal und ohne Cloud-Verbindung**. Es ergänzt die `e3dc_rscp`-Integration um eine regelbasierte Steuerung mit 17 priorisierten Phasen, vorausschauendem Laden, Abregelschutz, PV-Prognose, Tarifspreizung, Wallbox- und Wärmepumpenregelung sowie einem Auto-Optimierungsmodus.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg?style=for-the-badge)](LICENSE)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue?style=for-the-badge&logo=paypal)](https://www.paypal.com/paypalme/tommigraf)

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
8. [Dashboard einrichten](#dashboard-einrichten)
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
| **Anti-Flapping** | EWMA-Glättung von PV/Last (τ = 60 s, Jump-Reset bei 2 kW) + Feed-in-Limit-Hysterese + pv_delay-Cooldown verhindern schnelles Phasen-Pendeln |
| **Battery & PV Sizing Advisor (v0.3.7)** | 2D-Simulation (Zusatz-Akku × Zusatz-PV) auf historischen Stundendaten — berechnet Einsparung, Amortisation, Autarkie und drei Empfehlungen (wirtschaftlich / technisch / ausgewogen) |
| **Automatisierte Tests + CI** | Control-Engine, Forecast/PV-Parser, Optimizer und Sizing Advisor abgedeckt; GitHub Actions mit pytest, Ruff und hassfest |

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

> **✨ Auto-Erkennung:** Wenn die `e3dc_rscp`-Integration installiert ist, schlägt
> Maestro alle Sensoren automatisch vor (SoC, PV, Haus, Netz, Akku, Wallbox-Verbrauch).
> Auch das Vorzeichen der Netzleistung wird für `_transfer_to_from_grid` automatisch invertiert.
> Eine **openWB**-Wallbox wird ebenfalls erkannt (Pattern: `sensor.openwb_chargepoint*_ladeleistung`),
> ebenso eine vorhandene **EVCC-Integration** ([marq24/ha-evcc](https://github.com/marq24/ha-evcc),
> Domain `evcc_intg`). Du kannst alle Vorschläge überschreiben.

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

> **Korridor-Bypass nach Ziel-Ladeende (Phase 7d):** Ist die saisonale Ladeende-Stunde erreicht, der Ziel-SoC aber noch nicht voll, und liefert die PV weiter Strom, hebt Maestro den Korridor-Power-Cap auf (`charge_power_limit = Max. Ladeleistung`). Damit nutzt der E3DC den vollen PV-Surplus selbst, statt ihn aufgrund der EWMA-Glättung unnötig ans Netz einzuspeisen. Hinweis: Der Parameter **Sommermaximum Ladebeginn (h)** wird aktuell nicht mehr von der `decide()`-Engine ausgewertet und ist nur noch aus Kompatibilität sichtbar.

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

Steuert die Ladeleistung der Wallbox nach PV-Überschuss **und/oder** trennt den
Wallbox-Verbrauch sauber vom Hausverbrauch ab.

> **Hinweis zur nativen E3DC-Wallbox:** E3DC-Systeme regeln ihre integrierte Wallbox bereits eigenständig über das interne Energiemanagement — PV-Überschuss wird dabei automatisch zwischen Akku und Wallbox verteilt. Maestro kann über `set_wallbox_charging_current` nur den **maximalen Ladestrom begrenzen**, ersetzt aber nicht das E3DC-eigene Management. Der praktische Mehrwert für die native E3DC-Wallbox ist daher begrenzt.
>
> **Empfehlung:** Die Wallbox-Regelung ist primär sinnvoll für **Fremdwallboxen** (EVCC, generisch), die das E3DC nicht kennen und keine eigene Überschussregelung haben.

#### Verbrauchstrennung Haus / Wallbox (seit v0.3.1)

Wird ein **Wallbox-Powersensor** konfiguriert, separiert Maestro den EV-Ladeverbrauch vom Hausverbrauch.
Dadurch werden EWMA-Glättung, PV-Forecast und der Optimizer **nicht durch Ladespitzen verfälscht**.
Die Funktion ist unabhängig vom Schalter „Wallbox-Regelung“ — auch ohne aktive Maestro-Steuerung
kannst du den Powersensor einbinden, um saubere Statistiken zu erhalten.

| Parameter | Standard | Erläuterung |
|---|---|---|
| **Wallbox-Regelung** | aus | Aktiviert die Strombegrenzungs-Logik |
| **Wallbox-Typ** | e3dc | `e3dc` = integrierte E3DC-Wallbox (RSCP-Service); `generic` = openWB / EVCC / beliebige Wallbox via custom-Services |
| **Wallbox-Powersensor** | – | W-Sensor des Wallbox-Verbrauchs (z. B. `sensor.<gerät>_wallbox_consumption` oder `sensor.openwb_chargepoint_4_ladeleistung`). Auto-erkannt. |
| **Hausverbrauchszähler enthält die Wallbox bereits** | Auto | `false` bei E3DC-Wallbox (eigener Powermeter); `true` bei openWB am EVU-Hauptzähler. Ist die Option aktiv, wird der Wallbox-Wert vom Hausverbrauch abgezogen. |
| **Minimalstrom (A)** | 6 | IEC-61851-Minimum |
| **Maximalstrom (A)** | 16 | Maximal erlaubter Ladestrom |
| **Phasenanzahl** | 3 | 1 oder 3 Phasen |
| **Mindest-PV-Überschuss (W)** | 1 400 | Erst ab diesem Überschuss wird die Wallbox aktiviert |

**Neue Sensoren:** `sensor.e3dc_maestro_wallbox_leistung` (W), `sensor.e3dc_maestro_gesamtlast_leistung` (W = Haus + Wallbox), `sensor.e3dc_maestro_wallbox_energie_heute` (kWh, Energy-Dashboard-tauglich).

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

### Sensoren – Diagnose

Diagnose-Sensoren sind in der Entitätenliste unter der Kategorie **Diagnose**
gruppiert. Die meisten sind nach der Installation **aktiviert**. Nur besonders
schreibintensive Detailwerte sind standardmäßig deaktiviert und müssen manuell
eingeschaltet werden (`debug_log`, `abregelung_verhindert_heute`).

| Entity-ID | Name | Beschreibung | Default |
|---|---|---|---|
| `sensor.e3dc_maestro_abregelung_verhindert_heute` | Abregelung verhindert heute | Energie die durch Einspeiselimit-Eingriff (70%-Regel) gesichert wurde (Detailwert von `pv_verlust_verhindert`) | deaktiviert |
| `sensor.e3dc_maestro_dc_abregelung_verhindert_heute` | DC-Abregelung verhindert heute | Energie die durch Curtailment Guard (DC-seitige Überdimensionierung) gesichert wurde (Detailwert von `pv_verlust_verhindert`) | aktiv |
| `sensor.e3dc_maestro_notstromreserve_aktuell` | Notstromreserve (aktuell) | Aktuell berechneter Reserve-SoC (saisonal interpoliert) | aktiv (Diagnose) |
| `sensor.e3dc_maestro_notstromreserve_adaptiv` | Notstromreserve (adaptiv) | Verbrauchsadaptiv berechnete Reserve | aktiv (Diagnose) |
| `sensor.e3dc_maestro_ht_reserve_adaptiv` | HT-Reserve (adaptiv) | Adaptiv berechnete HT-Reserve | aktiv (Diagnose) |
| `sensor.e3dc_maestro_debug_log` | Debug-Log | Letzte 5 Regel-Logeinträge; nur sinnvoll wenn Debug-Logging eingeschaltet ist | deaktiviert |

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
| `switch.e3dc_maestro_vorausschauende_ladung` | Vorausschauende Ladung | Hebt das heutige Ladeziel an, wenn morgen wenig PV erwartet wird |

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

## Dashboard einrichten

Das Classic-Dashboard ([`dashboards/maestro_dashboard.yaml`](dashboards/maestro_dashboard.yaml))
bietet **10 Tabs** (inkl. **Sizing Advisor** seit v0.3.7) mit Übersicht, Steuerung,
Diagnose und What-If-Analyse. Seit der Community-Dashboard-Strategie muss es **nicht
mehr per YAML eingefügt** werden.

### Voraussetzungen

| Card | Installation |
|---|---|
| [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) | HACS → Frontend |
| [ApexCharts Card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |

Zusätzlich: **Home Assistant ≥ 2026.5** für den Eintrag unter *Community dashboards*
(ohne Picker bleibt der manuelle YAML-Import unten als Fallback).

### Empfohlen: Community-Dashboard (ein Klick)

1. Integration **E3DC Maestro** einrichten (oder HA neu starten, falls sie schon läuft)
2. Browser **hart neu laden** (damit das Strategy-Modul geladen wird)
3. **Einstellungen → Dashboards → Dashboard hinzufügen**
4. Unter **Community dashboards** **E3DC Maestro** wählen
5. Vorgeschlagenen Titel **E3DC Maestro** und Icon bestätigen → Anlegen

> Der URL-Pfad muss **`e3dc-maestro`** lauten (Hilfe-Links). Der Dialog schlägt
> den passenden Titel vor — bitte nicht umbenennen, bevor der Slug steht.

Das Dashboard erscheint in der Sidebar. Änderungen an Maestro-Releases aktualisieren
die Strategy-Vorlage; ein bereits angelegtes Storage-Dashboard bleibt unverändert,
bis du es löschst und neu anlegst.

### Fallback: Manueller YAML-Import

Falls der Community-Picker fehlt (ältere HA-Version) oder du YAML bevorzugst:

1. **Einstellungen → Dashboards → Dashboard hinzufügen**
2. Titel **E3DC Maestro** (Slug `e3dc-maestro`)
3. Drei-Punkte-Menü → **In YAML bearbeiten**
4. Inhalt von `maestro_dashboard.yaml` einfügen → Speichern

Oder in ein bestehendes Dashboard: Raw-Editor öffnen und YAML ersetzen.

### Variante: Modernes Dashboard (manuell)

Zusätzlich steht [`dashboards/maestro_dashboard_modern.yaml`](dashboards/maestro_dashboard_modern.yaml)
zur Verfügung (moderner Look, Live-Energiefluss). Es wird **nicht** automatisch
angeboten, weil am Dateianfang fünf **installationsabhängige** E3DC-Roh-Entity-IDs
angepasst werden müssen.

**Zusätzliche Custom Cards (HACS → Frontend):**

| Card | Installation |
|---|---|
| [button-card](https://github.com/custom-cards/button-card) | HACS → Frontend |
| [mini-graph-card](https://github.com/kalkih/mini-graph-card) | HACS → Frontend |
| [apexcharts-card](https://github.com/RomRider/apexcharts-card) | HACS → Frontend |
| [power-flow-card-plus](https://github.com/flixlix/power-flow-card-plus) | HACS → Frontend |

> **Wichtig:** Hilfe-Links brauchen den Slug **`e3dc-maestro-modern`** → Titel
> **E3DC Maestro Modern**.

**Vor dem Import** die Platzhalter
(`sensor.e3dc_pv_power`, `sensor.e3dc_house_power`,
`sensor.e3dc_grid_power`, `sensor.e3dc_battery_power`,
`sensor.e3dc_soc`) an deine echten E3DC-Sensoren anpassen, dann YAML wie beim
Fallback importieren.

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

Für detaillierte `[decide]`-Logzeilen (eine pro Regelzyklus, inkl. EWMA-geglätteter PV/Last-Werte, aktueller Phase und Begründung) folgendes in `configuration.yaml` ergänzen und HA neu starten:

```yaml
logger:
  logs:
    custom_components.e3dc_maestro: debug
```

Die Zeilen sehen so aus:

```
[decide] phase=corridor pv=4520W(ewma) house=890W(ewma) grid=-2510W bat=1120W soc=62% reason=Ladekorridor: SoC 62% → Ziel 75%, Leistung 1120W
```

Ideal um nachzuvollziehen warum eine bestimmte Phase zu einem Zeitpunkt aktiv war.

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

**GNU Affero General Public License v3.0 (AGPL-3.0)** – siehe [LICENSE](LICENSE)

E3DC Maestro ist **freie Software**: Du darfst sie unter den Bedingungen der AGPL-3.0 nutzen, studieren, weitergeben und verändern.

Was das in der Praxis bedeutet:

- ✅ Private und kommerzielle **Nutzung** ist erlaubt.
- ✅ Du darfst den Code **verändern** und deine Version weitergeben.
- ⚠️ Eine **veränderte Version, die du weitergibst** (z. B. als andere HACS-Integration, Fork, App, Firmware, …), **muss ebenfalls unter AGPL-3.0** stehen und ihr **vollständiger Quellcode muss verfügbar gemacht werden**.
- ⚠️ Wenn du eine **veränderte Version als Netzwerk-/Cloud-Service** betreibst (z. B. einen SaaS-Energie-Optimierer, mit dem Nutzer über ein Netzwerk interagieren), **musst du den vollständigen Quellcode dieser veränderten Version** diesen Nutzern zugänglich machen.
- ⚠️ Der ursprüngliche Copyright-Hinweis und die Lizenz müssen erhalten bleiben.

Die AGPL wurde bewusst gewählt, um die Control-Engine, den Optimizer und die Forecast-Logik in `custom_components/e3dc_maestro/` **offen und gemeinschaftlich** zu halten. Closed-Source-Forks oder proprietäre Cloud-Rebrands sind **nicht erlaubt**.

Für Fragen zu kommerzieller Lizenzierung oder Anwendungsfällen, die mit der AGPL nicht kompatibel sind, bitte den Autor über den Issue-Tracker kontaktieren.
