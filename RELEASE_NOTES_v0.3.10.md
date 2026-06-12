# E3DC Maestro v0.3.10 – Bugfix: Wrong battery SoC on device page

**Release type:** Bugfix release  
**Date:** 2026-06-12

Thanks to **Florian** for reporting this issue.

---

## Overview

v0.3.10 fixes the battery percentage shown next to the battery icon on the
**E3DC Maestro device page** in Home Assistant. The value could display
**100 %** even when the actual state of charge was much lower (e.g. **87 %**).

---

## 🐛 Fixed issue

### Device overview showed forecast max SoC instead of actual battery level

**Symptom:** On *Settings → Devices → E3DC Maestro*, the header battery icon
showed an incorrect percentage (often **100 %**), while the real battery SoC
from E3DC RSCP was significantly lower.

**Cause:** Home Assistant picks the first `sensor` entity on a device with
`device_class: battery` for that header display. Maestro had assigned
`device_class: battery` to the **24 h forecast** sensors
(`forecast_min_soc` / `forecast_max_soc`). The forecast maximum can reach
**100 %** when the simulation expects the battery to fill during the day —
this is not the live SoC.

**Fix:**

- New sensor **`sensor.e3dc_maestro_aktueller_soc`** (`Aktueller SoC`) mirrors
  the configured SoC input and is the sole Maestro sensor with
  `device_class: battery`.
- `device_class: battery` removed from the forecast min/max SoC sensors.

After updating, **reload the integration or restart Home Assistant** so entity
attributes are refreshed.

---

## 🆕 New entity

| Entity | Description |
|--------|-------------|
| `sensor.e3dc_maestro_aktueller_soc` | Current battery SoC (%) — used for the device-page battery icon |

---

## ⚙️ Changed files

- `custom_components/e3dc_maestro/sensor.py`
- `custom_components/e3dc_maestro/manifest.json`

---

## 🧪 Tests

305 tests passed.

---

## ⚠️ Breaking changes

None.
