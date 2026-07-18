# Changelog

Alle nennenswerten Änderungen an **E3DC Maestro** — aus Nutzersicht.

Neue Punkte bitte oben unter **[Unreleased]** ergänzen und beim Release in
einen eigenen Versionsabschnitt verschieben.

---

## [Unreleased]

- **Bugfix Auto-Optimizer 48 h:** Tag-2 ist Kalender-**morgen** (nicht Solcast
  „Tag 3“/Übermorgen). Fallback auf den konfigurierten Morgen-Sensor; Labels/Doku
  korrigiert
- **Modernes Dashboard** als zweite Variante:
  [`dashboards/maestro_dashboard_modern.yaml`](dashboards/maestro_dashboard_modern.yaml)
  (Live-Energiefluss, Graphen, Hilfe-Seiten wie im Classic-Dashboard)
- Auto-Optimierung bewertet Akku-Verschleiß realistischer (über den
  tatsächlichen Durchsatz) und zeigt Einsparungen verständlicher
- interne Code-Struktur aufgeräumt (kein Verhaltenswechsel für den Alltag)

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
