# Changelog

Alle nennenswerten Änderungen an **E3DC Maestro** — aus Nutzersicht.

Neue Punkte bitte oben unter **[Unreleased]** ergänzen und beim Release in
einen eigenen Versionsabschnitt verschieben.

---

## [Unreleased]

---

## [0.3.26] – Modern-Dashboard: Corner-Glow & SoC-Hero (2026-10-07)

### Changed
- **Corner-Glow global:** `base_card`, KPI, Power/PV/Haus, Money, Status-Chips und
  Action-Tiles nutzen `variables.accent` für Glow- und Icon-Farbe (Room-Card-Stil).
- **SoC-Hero:** Akkustand mit großem Prozentwert, Meta-Zeile (Ziel · Autonomie) und
  Progress-Ring ums Batterie-Icon statt zentriertem Donut.
- **Phase-Hero:** Live-Badge oben rechts, Phasen-Icon im Glow unten links — ohne Überlappung.
- **SoC-Sensor:** Dashboard-Platzhalter `sensor.e3dc_soc` →
  `sensor.e3dc_maestro_aktueller_soc` (Maestro-Sensor, unabhängig vom e3dc_rscp-Namen).
- Modern-Dashboard (#11): Schnellsteuerungs-Icons vergrößert (`size` / `--mdc-icon-size`
  56 px, inkl. `img_cell`). Reine CSS-`width` wirkte in button-card nicht zuverlässig.
- Prognose-Chart (#11): Netz-Prognose zeigt Einspeisung nach unten (−) und Bezug nach oben,
  analog zum Leistungs-Chart und typischen E3DC-Sensoren. Die Sensor-Attribute bleiben
  bei der Maestro-Konvention (+ = Einspeisung); nur die Chart-Anzeige wird gespiegelt.

### Behoben
- SoC-Karte: kaputtes Layout (Ring rechts, Text über dem Kreis) durch ein einziges
  HTML-`custom_field`.
- Corner-Glow: abgeschnittene Icons (SoC-Ring, Aktive Eingriffe) durch sanftere Positionierung.
- Phase-Hero: Symbol und „Live“-Badge überlappten sich nicht mehr.
- Phase-Hero / Cockpit: fehlende Phasen-Labels ergänzt (`fast_floor` → „Schnelllade-Boden“,
  `hard_soc_limit`, `morning_discharge`, `curtailment_guard`, …); Untertitel fällt auf
  die lesbare `reason` zurück statt auf den Enum-Rohwert.

---

## [0.3.25] – Akku-Prognose ohne Sprung bei „Jetzt“ (#9) (2026-10-05)

### Behoben
- Prognose-Chart (Issue #9): Die Akku-Prognose setzt die aktuell laufende Ladung/Entladung
  fort und klingt nach ca. 1 h auf den simulierten Wert ab, statt bei „Jetzt“ zu springen
  (`battery_anchor_w`).
- Prognose-Simulation: Vorzeichen von `grid_power` an die Maestro-Konvention angepasst
  (+ = Einspeisung, − = Bezug); ein Defizit wurde zuvor als Einspeisung gewertet.

---

## [0.3.24] – Prognose-Chart: ±24 h, Legende, Skala (#9) (2026-10-03)

### Changed
- Prognose-Chart (Issue #9): letzte plus nächste 24 h statt Kalendertag,
  Ist-Linien bis „Jetzt", Prognose-Serien nicht in der Legende (Klick blendet
  Ist und Prognose gemeinsam aus), Haus wieder braun, feste Leistungsskala
  (−4…16 kW) mit gemeinsamer Nulllinie zu 0 % SoC (YAML anpassbar).
  Der Chart bleibt bei den fünf Größen aus Issue #9 (PV, Haus, Netz, Akku, SoC).
  Extra-Verbraucher (Wallbox, Heizstab, …) bleiben in den bestehenden Karten;
  sie würden die Hauskurve überlagern und die Legende unbrauchbar machen.

---

## [0.3.23] – Prognose-Chart bis Tagesende (Issue #9) (2026-10-03)

### Added
- Classic- und Modern-Dashboard: neue Karte „Leistungen & SoC – Verlauf und Prognose" (Issue #9).
  Zeigt Ist-Verlauf (durchgezogen) und Maestro-Prognose (gepunktet) für PV, Haus,
  Netz, Akku und SoC. Der Sensor `forecast_trajectory` liefert dafür die neuen
  Attribute `pv_points`, `house_points`, `grid_points`, `battery_points`.

### Changed
- 24-h-Prognose nutzt jetzt die konfigurierte Solcast-/Forecast.Solar-Tagesprognose
  (heute und morgen) auch dann, wenn der Schalter „PV-Prognose-Verzögerung" aus ist.
  Die Regelung ist davon nicht betroffen (nur Anzeige-Prognose).
- Der aktuell gemessene Hausverbrauch wird in die Prognose eingeblendet und klingt
  innerhalb von ca. 2 h auf das Durchschnittsprofil ab (`consumption_anchor_w`).
- Die Prognose wechselt zum Folgetag-Profil bei lokaler Mitternacht
  (`day2_from_calendar`).
- Der Prognose-Chart zeigt einen Hinweis, auf welcher Datenbasis die Prognose beruht.

---

## [0.3.22] – Schwacher PV-Tag: keine Lade-Verzögerung mehr (2026-09-30)

### Behoben
- **Schwacher PV-Tag: Ladung wurde morgens weiter verzögert.** Nach v0.3.19
  wich nur der Morning-Cap dem gelatchten schwachen PV-Tag. `pv_delay`
  („Ladung verzögert, Sonne kommt noch“) und die Korridor-Pause hingen weiter
  an der Restprognose-Freigabe der Akku-Priorität. Beide weichen jetzt ebenfalls
  am gelatchten schwachen PV-Tag; sonnige Tage bleiben unverändert.
- **Englische Oberfläche (#5, #6, #8):** Config-Flow und Optionen haben
  vollständige englische Übersetzungen (`strings.json`, `translations/en.json`).
- **Modern-Dashboard (#5, #6, #8):** Power-Flow-Card-Plus-Felder auf das
  aktuelle Schema migriert; Überlappung und Umbruch im Phase-Hero behoben.

---

## [0.3.19] – Morning-Cap weicht auch am gelatchten schwachen PV-Tag (2026-09-23)

### Behoben
- **Morning-Cap vs. schwacher PV-Tag (Restlücke):** In v0.3.18 weicht der
  Morning-Cap der *aktuellen* Akku-Priorität. Die Priorität wird aber
  freigegeben, sobald die Restprognose den Bedarf rechnerisch deckt – typisch
  an Tagen mit sonnigem Vormittag und bewölktem Nachmittag. Dann blockiert der
  Cap wieder (1 W), der Vormittags-Überschuss geht ins Netz, und der Akku wird
  nachmittags nicht mehr voll. Morning-Cap weicht jetzt am **gelatchten**
  schwachen PV-Tag (Tagesprognose), unabhängig vom Restprognose-Release.
  Sonnige Tage behalten den Cap unverändert.

### Nach dem Update
HA neu starten. Auf schwachen PV-Tagen sollte die Phase morgens nicht mehr auf
`morning_cap` hängen bleiben, solange der Tag als schwacher PV-Tag erkannt ist.

---

## [0.3.18] – Morning-Cap weicht Akku-Priorität; Dashboard-Strategy; Wallbox-Netzschutz (2026-09-17)

### Behoben
- **Morning-Cap vs. Schwacher-PV-Tag:** An Tagen mit Akku-Priorität (schwache
  Tagesprognose bzw. unzureichende Restprognose) blockierte der Morning-Cap das
  Laden trotzdem (1 W-Limit), obwohl das Dashboard bereits „Akku-Ladung
  priorisiert“ anzeigte. Folge: Vormittags-Überschuss ging ins Netz, der Akku
  blieb niedrig und konnte nachmittags bei Bewölkung nicht mehr voll werden.
  Morning-Cap weicht jetzt der Akku-Priorität – analog zum Abregelschutz.
- **Timeout beim Öffnen des Community-Dashboards:** Lovelace wartet nur 5 Sekunden
  auf `ll-strategy-dashboard-e3dc-maestro`. Das Strategy-Modul wurde bisher nur
  als Extra-JS im Frontend-HTML geladen – bei gecachtem Frontend oft zu spät oder
  gar nicht. Es wird jetzt zusätzlich als Lovelace-Dashboard-Resource
  (JavaScript-Modul) registriert.

### Neu
- **Wallbox-Netzschutz:** Solange die Wallbox über der Schwelle lädt, hält Maestro
  die Akku-Entladung offen (kein künstliches Entlade-Limit), damit Defizite aus
  dem Hausakku gedeckt werden statt aus dem Netz. Schalter + Schwellenwert als
  Entities.

### Nach dem Update
HA neu starten, danach Browser hart neu laden (Cmd/Ctrl+Shift+R). Unter
Einstellungen → Dashboards → Ressourcen sollte
`/e3dc_maestro/frontend/e3dc-maestro-strategy.js` als JavaScript-Modul stehen.
Bei Lovelace im YAML-Modus den Eintrag dort manuell ergänzen (`type: module`).

---

## [0.3.17] – Dashboard: Akku-Priorität korrekt vom Ganztags-Flag getrennt (2026-08-28)

### Behoben
- **Irreführende Status-Meldungen im Dashboard:** Nach der v0.3.16-Bedarfsprüfung
  konnte das Dashboard weiterhin "Akku-Ladung priorisiert" anzeigen, obwohl das
  neue Gate (`battery_priority`) die Priorität bereits freigegeben hatte – die
  Status-Chips, die Warnzeile unter der Entscheidungserklärung und der
  "Eingriffe aktiv"-Zähler hingen alle am alten Ganztags-Flag
  `binary_sensor.e3dc_maestro_schwacher_pv_tag`, das nur die Tagesprognose
  widerspiegelt und nie mehr gegen den tatsächlichen Bedarf geprüft wird.
- **Neuer Binärsensor `binary_sensor.e3dc_maestro_akku_prioritat_aktiv`**
  (gebunden an `last_decision.battery_priority`) zeigt den tatsächlich aktiven
  Priorität-Status. Beide Dashboards (Classic & Modern) verwenden ihn jetzt für
  alle Live-Status-Anzeigen; `schwacher_pv_tag` bleibt als reiner
  Tages-Kontext-Sensor ("heute als PV-schwach erkannt") in den
  Diagnose-/Einstellungslisten erhalten und ist dort entsprechend beschriftet.

### Nach dem Update
HA neu starten oder Integration neu laden, danach Browser hart neu laden
(Cmd/Ctrl+Shift+R). Das Community-Dashboard ist eine Lovelace-Strategy und
übernimmt die Änderung automatisch.

---

## [0.3.16] – Schwacher-PV-Tag-Logik: Bedarfsprüfung statt Ganztags-Flag (2026-08-28)

### Geändert – Schwacher-PV-Tag-Logik: Bedarfsprüfung statt Ganztags-Flag

**Verhaltensändernd.** Die Schwacher-PV-Tag-Priorität (voller PV-Überschuss in
den Akku statt Spreading/Korridor-Pause) wurde bisher als Ganztags-Flag aus
dem Verhältnis Tagesprognose/Referenz-Sommertag abgeleitet und danach nie mehr
gegen den tatsächlichen Restbedarf geprüft. Das führte dazu, dass der Akku an
einem als "schwach" markierten Tag auch dann noch mit voller Leistung
weitergeladen wurde, wenn die Restprognose den Bedarf bis zum Ladeende-SoC
längst um ein Vielfaches deckte (Feldfall 28.08.2026: SoC 85 %, Restbedarf
2,7 kWh, P10-Restprognose 21,9 kWh, trotzdem 9000 W Ladeleistung).

- **Bedarfsprüfung als Gate:** Neue Kennzahl `low_yield_coverage_ratio()`
  (Restprognose ÷ Restbedarf bis Ladeende-SoC × Sicherheitsfaktor) deaktiviert
  die Priorität, sobald die Deckung ausreicht. Hysterese (Freigabe ab
  Deckungsgrad 1,0, Wiedereinstieg erst unter 0,85) verhindert Phasen-Pendeln.
  Ohne jede Restprognose bleibt das Altverhalten unverändert (Gate schließt,
  keine Regression für Installationen ohne PV-Prognose-Sensor).
- **Ziel-Konsistenz:** Im Prioritäts-Zweig zeigen `target_soc` und der
  Reason-Text jetzt das tatsächlich verfolgte Ladeende-SoC statt des an
  diesem Tick übersteuerten Tages-Rampenziels – behebt den Widerspruch
  "Ziel 67 %" bei einer Ladung, die tatsächlich bis 100 % läuft.
- **Diagnose:** Neues Attribut `low_yield_coverage` am
  `sensor.e3dc_maestro_decision_explanation` sowie im Reason-Text der
  Priorität.
- **Saisonal normierte Referenz (opt-in):** Neuer Parameter
  `low_yield_reference_seasonal` skaliert die kWp-Baseline-Referenz über die
  Tageslänge (Faktor 0,3–1,0 zwischen Winter- und Sommersonnenwende), damit
  `binary_sensor.e3dc_maestro_schwacher_pv_tag` im Winter nicht praktisch
  jeden Tag als "schwach" markiert. Standardmäßig aus – bestehende
  Installationen ändern sich nicht ohne explizite Aktivierung.
- **Ramp-Bypass entkoppelt:** Der sanfte Leistungsanlauf (A2) wird jetzt nur
  noch übersprungen, wenn die Priorität in diesem Tick tatsächlich aktiv war
  (`decision.battery_priority`), nicht mehr für den ganzen Tag über das
  Ganztags-Flag `low_yield_day_active`.
- **Zurückgestellt:** Eine zeitbasierte Dosierung im Übergangsband
  (Deckungsgrad 0,85–1,0) wurde bewusst nicht umgesetzt – `max_charge_power`
  ist an einem echt trüben Tag richtig, weil kurze Wolkenlücken sofort
  mitgenommen werden. Erst bei beobachteter Oszillation im Feld nachrüsten.

---

## [0.3.15] – Aktive Netzladung im low-Slot (NT-Fenster) (2026-08-28)

**Feature.** Follow-up zu [#2](https://github.com/TommiG1/hacs-e3dc-maestro/issues/2):
Ein `low`-Slot kann den Akku jetzt aktiv aus dem Netz nachladen — für klassische
NT-Verträge, um die Zeit bis zur PV-Deckung zu überbrücken.

### Neu
- **Aktive Netzladung im `low`-Slot (NT-Fenster):** Neue Phase `grid_charge`.
  Ist die Option **Aktive Netzladung im low-Slot** aktiviert, lädt Maestro in
  einem `low`-Tarif-Fenster **aktiv aus dem Netz** bis zum eingestellten
  **Netzlade-Ziel (% SoC)** — unabhängig vom Tarif-Modus. Damit überbrückt ein
  klassischer NT-Vertrag die Zeit bis zur PV-Deckung, statt später im teureren
  Normaltarif nachladen zu müssen (Follow-up zu
  [#2](https://github.com/TommiG1/hacs-e3dc-maestro/issues/2)). Die aus dem
  Netz geladene Energie ist durch das Tagesbudget **Max. Netzladung/Tag (kWh)**
  begrenzt (dieses wird jetzt erstmals in der Engine ausgewertet).
- **Prognosebasierte Netzlade-Menge (Option):** Mit **Netzlade-Menge
  prognosebasiert** lädt Maestro im `low`-Slot nur so viel nach, wie laut
  morgiger PV-/Verbrauchsprognose nötig ist (Defizit = Verbrauch − PV), statt
  stur bis zum festen Ziel-SoC. Der Ziel-SoC wirkt dann als Obergrenze; ohne
  Prognosedaten gilt weiterhin der feste Ziel-SoC.
- Neuer Binärsensor **Netzladung aktiv** (`binary_sensor.e3dc_maestro_netzladung_aktiv`).
- **Dashboard:** Neue Phase `grid_charge` in Classic- und Modern-Dashboard
  (Status-Chip „Netzladung", Phasen-Label/Farbe, Glossar) sowie im Tarif-Slots-
  Block. Das Community-Dashboard ist eine Lovelace-Strategy und aktualisiert
  sich automatisch – nach dem Update genügt **HA-Neustart + Browser-Hard-Refresh**
  (Cmd/Ctrl+Shift+R), kein Neu-Anlegen nötig.

### Doku
- Tarif-Slot-Beschreibung korrigiert: `low` ist ein günstiges Fenster mit
  optionaler aktiver Netzladung; `high` = Akku deckt Haus bis zur Reserve,
  darunter Entladesperre (die alte Formulierung „high = entladen sperren" war
  seit dem HT-Floor-Fix in v0.3.14 irreführend).

### Hinweis
Bislang war die `low`-Klasse rein passiv (sie hob nur das PV-Überschuss-Ceiling
auf, und das auch nur bei `tariff_mode=dynamic`). Nachts wurde daher gar keine
Netzladung ausgelöst. Wer das bisherige Verhalten will, lässt die neue Option
einfach deaktiviert (Standard).

---

## [0.3.14] – HT-Schutz Entladelogik korrigiert (2026-08-25)

**Bugfix.** Der HT-Schutz hat die Akku-Entladung im Hochtarif genau verkehrt
herum geregelt. Die Entladung wurde gesperrt, solange der SoC **über** der
HT-Reserve lag — also gerade dann, wenn der Akku das Haus versorgen sollte.
Erst wenn der Akku fast leer war, wurde entladen. Folge: voller Akku und
teurer Netzbezug im Hochtarif-Fenster (siehe [#2](https://github.com/TommiG1/hacs-e3dc-maestro/issues/2)).

### Behoben
- **Floor-Semantik wie bei der Notstromreserve:** Im `high`-Slot versorgt der
  Akku jetzt das Haus und entlädt bis zur HT-Reserve. Erst wenn der SoC die
  Reserve erreicht, stoppt die Entladung, damit für den Rest des teuren
  Fensters genug Kapazität bleibt. Netzladung findet im `high`-Slot weiterhin
  nicht statt.

### Doku
- README, Erklärungssensor und Dashboard-Hilfetexte auf die korrigierte
  Floor-Semantik angepasst (`high` = Entladung nur bis zur Reserve).

### Nach dem Update
HA neu starten oder Integration neu laden. Bestehende Konfiguration bleibt
unverändert; die HT-Reserve-Parameter wirken jetzt wie beschrieben als Floor.

---

## [0.3.13] – Dynamisches P10-Prognose-Gate für Spreading (2026-08-21)

**Feature / Bugfix.** Spreading darf nicht mehr drosseln, wenn die konservative
PV-Restprognose den Ladebedarf nicht deckt — sonst speist die Anlage ein,
während der Akku leer bleibt.

### Neu
- **Prognose-Gate (P10):** Vergleicht die pessimistische Rest-PV-Prognose
  (`estimate10` am konfigurierten Solcast-/Forecast-Sensor) mit dem
  Restbedarf × Sicherheitsfaktor. Ist P10 unzureichend, pausiert Spreading
  und Maestro priorisiert den Akku (voller PV-Überschuss statt Einspeisung)
- Gemeinsame **Akku-Priorität** aus Schwacher-PV-Tag **oder** unzureichender
  P10-Prognose
- Neuer Sensor **PV-Restprognose (P10)** inkl. Attributen P50-Rest und
  Sicherheitsfaktor
- Dashboard: P10/P50 in „Ladeverteilung“, Hilfetext zum Prognose-Gate

### Verhalten
- Fehlt P10 an der Prognosequelle → Fallback auf P50
- Ohne Forecast-Daten oder bei deaktiviertem Forecast/Spreading → Gate inaktiv
  (bisheriges Spreading bleibt unverändert)

### Nach dem Update
HA neu starten oder Integration neu laden, Browser hard-refreshen. Bestehende
Classic-Dashboards werden **nicht** überschrieben — zum Erneuern: Dashboard
löschen und über Community dashboards neu anlegen (oder YAML neu importieren).

---

## [0.3.12] – Community-Dashboard & Forecast-Härten (2026-07-18)

**Feature / Qualität.** Classic-Dashboard ohne YAML-Copy-Paste; 48‑h-Forecast
korrekt; Aktorik und HA-Integration robuster.

### Dashboard neu hinzufügen (Classic)

Voraussetzungen: **Home Assistant ≥ 2026.5**, HACS-Frontend
[Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) und
[ApexCharts Card](https://github.com/RomRider/apexcharts-card).

1. Integration auf **v0.3.12** aktualisieren (HACS) und **HA neu starten**
   (oder Integration neu laden)
2. Browser **hart neu laden** (damit das Strategy-Modul geladen wird)
3. **Einstellungen → Dashboards → Dashboard hinzufügen**
4. Unter **Community dashboards** **E3DC Maestro** wählen
5. Vorgeschlagenen Titel **E3DC Maestro** und Icon bestätigen → Anlegen

Der URL-Pfad muss **`e3dc-maestro`** lauten (Hilfe-Links). Den Titel im Dialog
nicht umbenennen, bevor der Slug gesetzt ist.

Bereits angelegte Dashboards werden durch Updates **nicht** überschrieben.
Zum Erneuern: altes Dashboard löschen und wie oben neu anlegen.

**Fallback** (ältere HA-Version ohne Community-Picker): YAML manuell aus
[`dashboards/maestro_dashboard.yaml`](dashboards/maestro_dashboard.yaml)
importieren, Titel **E3DC Maestro**.

**Modern-Dashboard** bleibt manueller Import
([`dashboards/maestro_dashboard_modern.yaml`](dashboards/maestro_dashboard_modern.yaml))
wegen installationsabhängiger Roh-Entity-IDs.

### Weitere Änderungen
- **Bugfix Auto-Optimizer 48 h:** Tag-2 = Kalender-**morgen**; Fallback auf
  Morgen-Sensor; `ignore_date` nur noch bei eintägigen Sensoren
- Forecast mit aktiven Auto-Parametern, Solcast-Tagesprofil, Executor; Retry
  nach Optimizer-Fehlern
- RSCP-/Aktor-Aufrufe serialisiert im Hintergrund (Polling blockiert nicht)
- Diagnose-Entitäten als `EntityCategory.DIAGNOSTIC`; Geräte-`sw_version` aus
  Manifest; HA Diagnostics-Plattform
- CI (pytest/ruff/hassfest), Dashboard-Validator, Glossar an `decide()`-Priorität
- Auto-Optimierung: realistischerer Akku-Verschleiß über Durchsatz
- interne Modularisierung (Tarif, Selectors, PV-Parser)

### Nach dem Update
HA neu starten oder Integration neu laden, Browser hard-refreshen, dann
Dashboard wie oben anlegen bzw. prüfen.

---

## [0.3.11] – Lade-Cap blieb hängen (2026-06-21)

**Bugfix.** An sonnigen Tagen konnte der Akku stundenlang nur mit einem
winzigen Limit (z. B. 51 W) laden, obwohl Maestro intern schon ~2 kW
wollte — der Überschuss ging ins Netz.

### Behoben
- Maestro vergleicht Soll-Werte jetzt mit dem **zuletzt an die E3DC
  gesendeten** Cap (vorher konnte der Debounce Updates blockieren)
- Kein „Mini-Cap-Snapshot“ mehr im erweiterten Korridor, der die echte
  Spreading-Rate überdeckt
- Nach Phasenwechseln holt das Cap schneller zum echten Bedarf auf
- Beim Laden wird die Entladung für den Hausverbrauch explizit freigegeben

### Neu / sichtbarer
- Sensoren **Gesendetes Lade-/Entlade-Limit** (Soll vs. tatsächlich gesendet)
- Anzeigenamen: „Aktives …-Limit“ → **Soll-…-Limit** (Entity-IDs unverändert)
- Dashboard: Soll/Gesendet-Kacheln, orange Markierung bei Drift

### Nach dem Update
Integration neu laden oder HA neu starten, Dashboard im Browser hard-refreshen.

---

## [0.3.10] – Falscher SoC auf der Geräte-Seite (2026-06-12)

**Bugfix.** Auf der HA-Geräte-Seite von Maestro konnte das Batterie-Icon
**100 %** zeigen, obwohl der echte SoC z. B. 87 % war.

### Ursache & Fix
Forecast-Sensoren (Min/Max-SoC) hatten fälschlich `device_class: battery`.
Neu: **`sensor.e3dc_maestro_aktueller_soc`** ist der einzige Maestro-Sensor
mit Batterie-Klasse und zeigt den echten SoC.

Danke an **Florian** für den Hinweis.

### Nach dem Update
Integration neu laden oder HA neu starten.

---

## [0.3.9] – Schwacher-PV-Tag: Akku zuerst (2026-06-09)

**Feature.** An bewölkten Tagen (Tagesprognose deutlich unter dem
Referenz-Ertrag) priorisiert Maestro die **Akku-Ladung vor Einspeisung**:
kein Spreading/Korridor-Drosseln — der E3DC nutzt den PV-Überschuss selbst
(`NORMAL` + festes Lade-Cap).

### Einrichtung
In den Integrations-Optionen unter **PV-Prognose** den Sensor
„Prognose heute – Tagessumme kWh“ setzen (z. B. Solcast). Ohne Sensor
greift die Erkennung nicht.

### Neu (Auszug)
- Schalter / Binärsensor „Schwacher-PV-Tag“
- Sensoren für Tagesprognose, Referenz-Ertrag und Quote
- Schwelle und Referenz-Parameter als Number-Entities

Feature ist standardmäßig **an**; ohne Prognose-Sensor passiert nichts.

---

## [0.3.8] – Ungewolltes Vollladen in der Pause (2026-05-28)

**Bugfix.** In der Korridor-Pause konnten Limits freigegeben werden —
manche E3DC-Setups luden dann mit **vollem PV-Überschuss**, obwohl Maestro
pausieren wollte. Die Pause blockiert die Ladung jetzt aktiv (Entladung
bleibt frei).

---

## [0.3.7] – Battery & PV Sizing Advisor (2026-05-14)

**Feature.** Neuer **Sizing Advisor**: aus deinen HA-Historiedaten
abschätzen, was zusätzliche Batteriekapazität und/oder mehr PV bringen
würde (Einsparung, Amortisation).

Zusätzlich: **Navigationsmenü** im Options-Dialog — Bereiche direkt
anwählen statt 14 Schritte hintereinander.

### Nach dem Update
Energie-Sensoren für den Advisor in den Optionen prüfen (Auto-Detect
hilft). Analyse im Dashboard-Tab starten.

---

## [0.3.6] – Adaptive Reserve & Korridor-Pause (2026-05-13)

**Bugfix.**
- Adaptive Reserve konnte Entladung ab ~90 % SoC sperren — Max-Deckel
  jetzt sinnvoller (Standard 35 %) und im UI einstellbar
- Korridor-Pause greift auch mit erweitertem Korridor bei kleinem
  Überschuss korrekt
- Dashboard: tote/falsche Entity-Verweise bereinigt

Danke an **@roedi02** im HA-Community-Forum.

---

## [0.3.5] – Schnelllade-Boden & erweiterter Korridor

**Feature** (beide optional, standardmäßig aus):

- **Schnelllade-Boden:** Unter einem SoC-Boden (z. B. 40 %) mit vollem
  PV-Überschuss laden, danach normale Tagesrampe
- **Erweiterter Ladekorridor:** Ladeleistung proportional zum Abstand
  zum Tagesziel (unten/oben konfigurierbar)

Keine Migration nötig — neue Entities erscheinen automatisch.

---

## [0.3.4] – Korridor-Bypass & Auto-Tuning

- Nach Erreichen des Ladeende-Ziels unnötige Netzeinspeisung vermeiden
  (Korridor-Bypass / Phase 7d)
- Auto-Optimizer feiner abgestimmt
- Hard-SoC-Limit und PV-Verzögerung klarer im Dashboard getrennt

---

## [0.3.3] – Forecast bei leerem Akku

**Bugfix.** Die 24‑h-SoC-Prognose verbuchte Netzbezug falsch, wenn der
Akku leer war — Forecast und Auto-Optimierung sind dadurch stimmiger.

---

## [0.3.2] – Pause lud trotzdem voll

**Bugfix.** In PV-Verzögerung, Korridor-Pause und Spreading-Pause wurden
Limits freigegeben → E3DC lud mit vollem Überschuss. Diese Phasen setzen
jetzt aktiv `max_charge = 0` (Hausversorgung aus dem Akku bleibt möglich).

---

## [0.3.1] – Wallbox, Auto-Detect & Spreading-Schutz

**Qualitäts-Release.**

- Wallbox-Verbrauch vom Hausverbrauch trennbar (openWB/EVCC/E3DC)
- Auto-Erkennung für RSCP-Sensoren, Systemparameter, openWB und EVCC
- Option „Vorzeichen Netzleistung invertieren“ (fix für `Netzbezug heute = 0`)
- Spreading wird per Migration standardmäßig aktiviert (weniger
  0/max-Lade-Bursts) — jederzeit wieder abschaltbar

### Nach dem Update
Einmal den Konfigurations-Wizard durchlaufen lassen. Wenn Netzbezug
weiterhin 0 ist: Quell-Sensor auf `*_transfer_to_from_grid` und Invert
aktivieren (Auto-Detect schlägt das vor).

---

## [0.3.0] – Vorausschauende Auto-Optimierung

**Feature.**
- Auto-Optimierung mit bis zu **48 h** Horizont und echten PV-Prognosen
  (Solcast / Forecast.Solar)
- feinere Prognose-Auflösung (15/30 min) — wichtig für 70 %-Einspeisegrenzen
- Kosten/Erlöse bleiben über HA-Neustarts erhalten
- Lizenz: **MIT → AGPL-3.0**

In vielen Setups reicht die Auto-Optimierung allein; Extra-Features
(Vorentladung, Spreading, Morning-Cap, …) nur bei Bedarf zuschalten.
