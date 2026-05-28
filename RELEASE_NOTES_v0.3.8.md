# E3DC Maestro v0.3.8 – Bugfix: Prevent unintended full-power charging

**Release-Typ:** Bugfix-Release  
**Datum:** 28.05.2026

---

## Übersicht

v0.3.8 behebt einen Live-Fall, in dem der Wechselrichter den Akku mit **vollem PV-Überschuss** laden konnte, obwohl Maestro effektiv in einer *Pause / Idle*-Situation war.

---

## 🐛 Behobene Probleme

### Post-ceiling Korridor-Pause: `clear_power_limits` → volle PV-Überschussladung

**Symptom:** In einzelnen Situationen (z. B. kurzzeitig unterschätzter nutzbarer Überschuss) wurde die Korridor-Pause aktiv, Maestro gab aber die Limits frei. Auf manchen E3DC-Setups führt das zu einem Rückfall auf das Default-Verhalten: **Laden mit voller PV-Überschussleistung**.

**Ursache:** In der Post-ceiling Korridor-Pause wurde bisher

- `charge_power_limit = None` zurückgegeben → Coordinator sendet `clear_power_limits`

**Fix:** Die Post-ceiling Korridor-Pause blockiert die Ladung nun aktiv:

- `charge_power_limit = 0.0` → Ladung blockiert (Entladung bleibt frei, Normal-Mode)

---

## ⚙️ Geänderte Dateien

- `custom_components/e3dc_maestro/control_engine.py`
- `custom_components/e3dc_maestro/explanation.py`
- `tests/test_control_engine.py`

