# E3DC Maestro v0.3.6 – Adaptive Reserve Bugfix & Dashboard Cleanup

**Release-Typ:** Bugfix-Release
**Datum:** 13.05.2026

---

## 🐛 Behobene Probleme

### Adaptive Reserve sperrte Entladung bei hohem SoC
**Symptom (von @roedi02 im HA-Community-Forum gemeldet):**
Mit aktivierter *Adaptive Reserve* und *Saisonaler Notstromreserve* hörte die
Batterie bei rund 90 % SoC mit der Entladung auf und wechselte in den Zustand
`reserve_protection` – unabhängig von den eingestellten Winter-/Äquinoktium-
Werten (15 % / 10 %). Nach Deaktivierung der Adaptive Reserve setzte die
Entladung sofort ein.

**Ursache:**
Der interne Deckel `adaptive_reserve_max_soc` hatte einen Default von **90 %**.
Die Berechnung

```
needed_kWh = avg_w_24h × 24 h × safety_factor (1.3) / battery_capacity_kWh
reserve_%  = needed_kWh × 100  → clamped auf [min_soc, max_soc]
```

ergibt bei typischen Haushalten (>150 W Durchschnittslast, ≤15 kWh Batterie)
schnell Werte > 90 %, die auf 90 % geclampt wurden. Damit überstimmte die
adaptive Reserve die statischen Saisonwerte komplett und sperrte fast jede
Entladung.

**Fix:**
- `DEFAULT_ADAPTIVE_RESERVE_MAX_SOC`: **90 % → 35 %**
- Default in `MaestroParams.adaptive_reserve_max_soc` ebenfalls auf 35 %
- Parameter ist jetzt im *Config-Flow* (Geräte-Einstellungen) konfigurierbar
  (Bereich 5–90 %), bisher war er nur intern gesetzt.

### Tote / falsch benannte Entities im Dashboard
Drei Dashboard-Einträge verwiesen auf Entitäten, die in aktuellen Releases
unter anderen IDs registriert werden (Neu-Installationen waren betroffen,
Bestandsinstallationen hatten die alten IDs noch im Entity-Registry):

| Vorher | Nachher |
|---|---|
| `number.e3dc_maestro_powerfaktor` *(in v2-Migration entfernt)* | **entfernt** |
| `number.e3dc_maestro_morning_cap_aktiv_bis_uhr_gmt` | `..._morning_cap_aktiv_bis_uhr_lokal` |
| `sensor.e3dc_maestro_saisonales_ladeende_stunde` | `..._saisonales_ladeende_uhrzeit` |

---

## ✨ Neu

### Adaptive Reserve – Max-SoC-Deckel im UI
Der bisher hartcodierte Parameter `adaptive_reserve_max_soc` ist nun im
Konfigurations-Dialog der Integration sichtbar (*Einstellungen →
Integrationen → E3DC Maestro → Konfigurieren → Adaptive Reserve*).

**Empfehlung:** 25–40 %. Höhere Werte nur bei sehr großen Batterien
und/oder explizitem Reserve-Bedürfnis.

### Erweiterte Hilfe für Adaptive Reserve
Die Hilfe-Seite *Hilfe → Adaptive Reserve* im Dashboard wurde um einen
Abschnitt zum neuen *Max. SoC-Deckel* erweitert (inkl. Beispielrechnung).

---

## � Behobene Probleme (13.05.2026 – Hotfix)

### Korridor-Pause griff nicht bei `advanced_corridor` + kleinem PV-Überschuss

**Symptom:**
Mit aktiviertem *Erweitertem Ladekorridor* (`advanced_corridor=True`) speiste
das System ins Netz ein und der Akku entlud sich leicht (~93 W), obwohl
PV-Überschuss vorhanden war und der SoC das Ziel noch nicht erreicht hatte.

**Ursache (Reihenfolge-Bug in `decide()`):**
Die bisherige Korridor-Pause **7b** prüfte `charge_power < lower_corridor`
*vor* `_apply_house_ceiling`. Bei `advanced_corridor` berechnet sich die
Soll-Ladeleistung aus dem SoC-Delta:

```
charge_power = lower_corridor + (soc_delta/100) × (upper_corridor − lower_corridor)
             = 1500 + (10/100) × (9000−1500) = 2250 W  →  weit über 1500 W → Pause griff nicht
```

`_apply_house_ceiling` reduzierte danach auf den verfügbaren EWMA-Surplus
(~294 W). Das resultierende Limit von 294 W wurde dennoch an den E3DC
gesendet. Die E3DC-Hardware ignorierte dieses kleine Limit zugunsten einer
bereits aktiven RSCP-State-Sperre und speiste stattdessen ein.

**Fix – Neuer Check 7e (Post-Ceiling Corridor Pause):**
Nach `_apply_house_ceiling` wird geprüft, ob `effective_charge < lower_corridor`.
Trifft das zu, sendet Maestro `charge_power_limit=None` (`clear_power_limits`)
statt eines kontraproduktiven kleinen Limits. Der Wechselrichter regelt den
verbleibenden Surplus dann selbst direkt in den Akku.

Der Curtailment Guard bleibt weiterhin ausgenommen (überschreibt die Pause
wie bisher), damit abzuregelnde PV-Leistung weiter als Senke in den Akku
kann.

---

## 📦 Geänderte Dateien

```
custom_components/e3dc_maestro/config_flow.py       (+3)
custom_components/e3dc_maestro/const.py             (Default 90 → 35)
custom_components/e3dc_maestro/control_engine.py    (MaestroParams Default 90 → 35; Fix 7e Post-Ceiling Pause)
custom_components/e3dc_maestro/strings.json         (Label adaptive_reserve_max_soc)
custom_components/e3dc_maestro/translations/de.json (Label adaptive_reserve_max_soc)
dashboards/e3dc_maestro.yaml                        (powerfaktor entfernt)
dashboards/maestro_dashboard.yaml                   (Entity-Fixes + Hilfe-Erweiterung)
tests/test_control_engine.py                        (+6 Tests: Regression Adaptive Reserve + Post-Ceiling Pause)
```

---

## 🧪 Tests

- **183 / 183 Tests bestehen** im `control_engine`-Testpaket
- Neue Regressions-Tests:
  - `test_high_consumption_clamped_to_new_default_max`
    bestätigt Clamping auf 35 % bei hohem Durchschnittsverbrauch
  - `test_bug_regression_high_load_soc89_not_blocked`
    bestätigt, dass `reserve_protection` bei SoC 89 % nicht mehr auslöst

---

## 🔁 Upgrade-Hinweise

### Für Bestandsnutzer mit aktivierter Adaptive Reserve
Nach dem Update gilt der neue Default-Cap von **35 %**. Wer bewusst einen
höheren Wert nutzen möchte, kann dies jetzt direkt im UI einstellen.

### Für Dashboard-Probleme
Bitte das Dashboard **als Raw-YAML neu importieren**, damit die korrigierten
Entity-IDs übernommen werden:

1. Dashboard öffnen
2. Drei-Punkte-Menü → *Dashboard bearbeiten* → *Raw-Konfigurationseditor*
3. Inhalt von `dashboards/maestro_dashboard.yaml` aus diesem Release einfügen
4. Speichern

---

## 🙏 Credits

- **@roedi02** für den ausführlichen Bug-Report im Home-Assistant-Forum
  ([Topic-Thread](https://community.home-assistant.io/t/e3dc-maestro-intelligent-battery-control-for-e3dc-home-storage-systems-hacs-custom-integration/1008767/14))
