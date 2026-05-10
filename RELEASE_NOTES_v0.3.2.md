# v0.3.2 – Bugfix: Lade-Sperre in pv_delay / Korridor-Pause / Spreading-Pause

Patch-Release für einen im Live-Betrieb (10.05.2026) aufgedeckten Regelfehler.
Reine Fehlerbehebung — keine neuen Features, keine Konfigurationsänderungen,
keine Migration nötig.

## ⬆️ Upgrade-Hinweis

Einfach via HACS aktualisieren. HA lädt die Integration automatisch neu.
Kein Wizard-Durchlauf, kein HA-Neustart erforderlich.

## 🐛 Bugfix

- **`pv_delay` / Korridor-Pause / Spreading-Pause sendeten keine Lade-Sperre an den E3DC.**
  Die drei Phasen lieferten `charge_power_limit=None`, was im Coordinator zu
  `clear_power_limits` führte – der Wechselrichter fiel auf seinen Default
  zurück und lud mit voller PV-Überschussleistung, obwohl die Phase
  ausdrücklich „Ladung pausieren" entschied.
  Beobachtbarer Effekt: bis zu 8 kW Ladestrom in Phase `pv_delay`.

  **Fix:** Alle drei Phasen senden jetzt `max_charge=0` an den E3DC.
  Die Entladung bleibt explizit frei (`discharge_power_limit=None`,
  `power_mode=NORMAL`) — das Haus darf bei kurzen PV-Einbrüchen weiter aus
  dem Akku versorgt werden; nur die Notstromreserve-Phase sperrt zusätzlich
  die Entladung.

- **`pv_delay` Spreading-Konflikt** (Folge des obigen Bugs):
  `pv_delay` hat bei guter PV-Prognose die Spreading-Phase preempted und
  damit die zeitbasierte gleichmäßige Ladekurve unterdrückt.

  **Fix:** Bei aktivem Spreading und SoC < 98 % wird `pv_delay` übersprungen
  – analog zur bestehenden Korridor-Pause-Exemption. Spreading bleibt damit
  der dominante Modus für die sanfte Tagesladung.

## ✅ Tests

- 234 Unit-Tests grün (3 neue Tests für die Phasen-Entscheidungen, u. a.
  `test_pv_delay_skipped_when_spreading_enabled` und
  `test_pv_delay_blocks_charging_but_allows_discharge`).

## 🔗 Bezug zu v0.3.1

Alle Features, Auto-Erkennungen und der Spreading-Hardware-Schutz aus
[v0.3.1](RELEASE_NOTES_v0.3.1.md) sind unverändert enthalten. v0.3.2
ist ein reiner Bugfix-Patch obendrauf.
