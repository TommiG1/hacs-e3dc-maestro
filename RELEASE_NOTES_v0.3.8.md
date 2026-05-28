# E3DC Maestro v0.3.8 – Bugfix: prevent unintended full-power charging

**Release type:** Bugfix  
**Date:** 2026-05-28

---

## Summary

This release fixes a real-world scenario where the inverter could start charging the battery at **full PV surplus power** even though Maestro was effectively in a “pause / idle” situation.

---

## What was happening?

Under certain conditions Maestro would enter an **idle pause** after applying the house-surplus ceiling (post-ceiling corridor pause). In that branch it previously returned:

- `charge_power_limit = None` → coordinator sends `clear_power_limits`

On some E3DC setups this means the inverter falls back to its internal default behaviour, which can immediately result in **full-power PV-surplus charging**.

---

## Fix

The post-ceiling corridor pause now **actively blocks charging** instead of freeing limits:

- `charge_power_limit = 0.0` → charging is blocked while discharge remains free (normal mode)

This prevents the inverter from switching to an uncontrolled default charging mode during the pause.

---

## Changed files

- `custom_components/e3dc_maestro/control_engine.py`
- `custom_components/e3dc_maestro/explanation.py`
- `tests/test_control_engine.py`

