# v0.3.4 – Korridor-Bypass nach Ziel-Ladeende & Auto-Optimizer-Tuning

Feature-/Bugfix-Release. Behebt unnötige Netzeinspeisung am Nachmittag,
optimiert den Auto-Optimizer-Suchraum und stabilisiert Diagnose-Logs.

## ⬆️ Upgrade-Hinweis

Via HACS aktualisieren. HA lädt die Integration automatisch neu. Keine
Konfigurationsänderung, keine Migration nötig. Live-Verhalten ändert sich
erst, sobald die saisonale Ladeende-Stunde erreicht ist und der Ziel-SoC
noch nicht voll ist.

## 🐛 Bugfix: Unnötige Netzeinspeisung am Nachmittag (Phase 7d)

**Problem:** Bei aktivem Ladekorridor und vorhandenem PV-Überschuss wurde
nicht der gesamte Surplus in den Akku geladen — stattdessen ging Strom ans
Netz (Einspeisung), obwohl der Akku noch nicht voll war.

**Ursache:** `_apply_house_ceiling()` cappte die Korridor-Ladeleistung an
der **EWMA-geglätteten** PV-Haus-Differenz. Diese Glättung läuft dem realen
Surplus hinterher → bei volatiler PV (Wolken, Lastsprünge) wird der Akku
gebremst, während echter Überschuss bereits ins Netz fließt.

**Fix:** Neue **Phase 7d** im decide-Engine. Sobald die saisonale
Ladeende-Stunde (`seasonal_charge_end_hour`) erreicht ist, der Ziel-SoC aber
noch nicht voll ist und PV weiterhin liefert, wird der Korridor-Power-Cap
aufgehoben: `charge_power_limit = params.max_charge_power`. Der E3DC nutzt
dann den vollen PV-Surplus selbst.

**Live-Verifikation:** Akku-Ladung 192 W → 1368 W, Grid −311 W → −15 W
direkt nach Aktivierung.

## ✨ Auto-Optimizer-Tuning

- **Kandidatenraum reduziert** von 64 → 16 Kombinationen (4 SoC × 4 until_h).
  Schnellere Konvergenz, weniger CPU-Last bei nächtlichen
  Optimierungsläufen.
- **`_build_candidate()` vereinfacht:** 2-Param-Signatur (`cap_soc`,
  `until_h`). `overrides`-Dict enthält nur noch `morning_cap_*`.

## 🔧 Stabilität / Diagnose

- **PV-Sensor-Autodetect:** Ein-Mal-Warnung statt Logspam jeder
  Coordinator-Cycle. `_autodetected_pv_sensor` als Cache, INFO-Log statt
  WARNING.
- **PV-Prognose-Verzögerungs-Schalter**
  (`switch.e3dc_maestro_pv_prognose_verzogerung`) jetzt separat von
  „Vorausschauender Ladung" toggelbar — saubere Trennung beider
  Mechanismen.

## 🛡️ Dashboard-Generator

`scripts/write_dashboard.py` ist out-of-sync mit dem manuell gepflegten
YAML. Generator hat jetzt einen Warn-Header und verweigert den Lauf ohne
`--force`. Schützt vor versehentlicher Zerstörung produktiver
Dashboard-Sektionen (Erträge & Kosten, Auto-Strategie-Card,
Help-Kostenmodul-Subview etc.).

## 📊 Dashboard-Erweiterungen

- **Hard-SoC-Limit (Akku-Deckel)** im Ladekorridor-Block: `switch` +
  `number` für Akkuschonung.
- **PV-Prognose-Verzögerung aktiv** im PV-Verzögerung-Block.
- Neue Hilfe-Sektionen für **Hard-SoC-Limit** und **Korridor-Bypass
  (Phase 7d)**.
- Statushinweis für `summer_maximum_hour`: derzeit ungenutzt (von
  `decide()`-Engine nicht ausgewertet).

## 📚 Doku

- [`README.de.md`](README.de.md): Hinweis-Box zu Phase 7d und Status
  `summer_maximum_hour`.
- Übersetzungen (`strings.json`, `de.json`): `summer_maximum_hour` als
  „derzeit ungenutzt" markiert.

## ⚠️ Bekannte Limitierungen / Offene Punkte

- `number.e3dc_maestro_summer_maximum_hour` ist Dead-Param (nicht mehr in
  `decide()` verwendet). Entfernung in einer späteren Version geplant.
- Auto-Optimizer enthält den Korridor-Bypass nicht als explizite
  Suchdimension — wirkt nur passiv über die Decide-Engine.

## ✅ Tests

235 Unit-Tests grün (keine Regression, keine neuen Tests in diesem
Release).
