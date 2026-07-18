"""Constants for E3DC Maestro."""
from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "e3dc_maestro"
NAME = "E3DC Maestro"


def _load_manifest_version() -> str:
    """Read version from manifest.json (single source of truth)."""
    manifest_path = Path(__file__).with_name("manifest.json")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "0.0.0"
    return str(data.get("version", "0.0.0"))


VERSION = _load_manifest_version()

# Integration expects e3dc_rscp to be configured
E3DC_RSCP_DOMAIN = "e3dc_rscp"

# Services provided by e3dc_rscp that we call
SERVICE_SET_POWER_LIMITS = "set_power_limits"
SERVICE_CLEAR_POWER_LIMITS = "clear_power_limits"
SERVICE_SET_POWER_MODE = "set_power_mode"
SERVICE_MANUAL_CHARGE = "manual_charge"
SERVICE_SET_WALLBOX_CURRENT = "set_wallbox_charging_current"

# Power modes
POWER_MODE_NORMAL = "normal"
POWER_MODE_IDLE = "idle"
POWER_MODE_CHARGE = "charge"
POWER_MODE_CHARGE_FROM_GRID = "charge from grid"
POWER_MODE_DISCHARGE = "discharge"

# Config entry keys – source entities (Step 1)
CONF_SOC_SENSOR = "soc_sensor"
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_ADDITIONAL_GENERATION_SENSOR = "additional_generation_sensor"
CONF_HOUSE_POWER_SENSOR = "house_power_sensor"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"          # positive = feed-in
CONF_GRID_POWER_INVERT = "grid_power_invert"          # bool: True = invert sign (sensor liefert positiv = Bezug)
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor"    # positive = charging
CONF_BATTERY_CHARGED_TODAY_SENSOR = "battery_charged_today_sensor"        # kWh, optional native daily counter
CONF_BATTERY_DISCHARGED_TODAY_SENSOR = "battery_discharged_today_sensor"  # kWh, optional native daily counter

# Config entry keys – system (Step 2)
CONF_INVERTER_POWER = "inverter_power"                # W, e.g. 12000
CONF_MAX_CHARGE_POWER = "max_charge_power"            # W, e.g. 3000
CONF_FEED_IN_LIMIT_PERCENT = "feed_in_limit_percent"  # % of installed kWp
CONF_INSTALLED_KWP = "installed_kwp"                  # kWp, e.g. 10.0
CONF_MIN_CHARGE_POWER = "min_charge_power"            # W, e.g. 300
CONF_UPDATE_INTERVAL = "update_interval"              # seconds, default 30

# Config entry keys – season / corridor (Step 3)
CONF_CHARGE_THRESHOLD = "charge_threshold"            # % SoC, e.g. 15
CONF_CHARGE_TARGET = "charge_target"                  # % SoC, e.g. 85
CONF_WINTER_MINIMUM_HOUR = "winter_minimum_hour"      # hour of day, e.g. 11
CONF_SUMMER_MAXIMUM_HOUR = "summer_maximum_hour"      # hour of day, e.g. 14
CONF_SUMMER_CHARGE_END = "summer_charge_end"          # fractional hour, e.g. 18.5
CONF_ADVANCED_CORRIDOR = "advanced_corridor"          # bool, show advanced params
CONF_LOWER_CORRIDOR = "lower_corridor"                # W
CONF_UPPER_CORRIDOR = "upper_corridor"                # W
CONF_FAST_CHARGE_FLOOR_ENABLED = "fast_charge_floor_enabled"  # bool
CONF_FAST_CHARGE_FLOOR_SOC = "fast_charge_floor_soc"          # % SoC – Schnelllade-Boden

# Config entry keys – HT/NT peak protection (Step 4)
CONF_HT_ENABLED = "ht_enabled"
CONF_HT_ON = "ht_on"                                  # hour local time (HA tz), e.g. 6
CONF_HT_OFF = "ht_off"                                # hour local time (HA tz), e.g. 21
CONF_HT_MIN = "ht_min"                                # % SoC at winter solstice
CONF_HT_SOCKEL = "ht_sockel"                          # % SoC at equinox
CONF_HT_SAT = "ht_sat"                                # bool
CONF_HT_SUN = "ht_sun"                                # bool

# Config entry keys – dynamic tariffs (Step 5)
CONF_DYNAMIC_TARIFF_ENABLED = "dynamic_tariff_enabled"
CONF_PRICE_SENSOR = "price_sensor"                    # entity_id
CONF_CHEAP_THRESHOLD = "cheap_threshold"              # €/kWh
CONF_MAX_GRID_CHARGE_KWH = "max_grid_charge_kwh"      # per day

# Phase C: generic tariff slot list (replaces the single HT-window).
# Stored under entry options as a list of dicts:
#   {"weekdays": [0,1,2,3,4], "start_h": 5, "end_h": 21,
#    "class_": "high", "min_reserve_soc": 50}
CONF_TARIFF_SLOTS = "tariff_slots"

# Config entry keys – wallbox (Step 6)
CONF_WALLBOX_ENABLED = "wallbox_enabled"
CONF_WALLBOX_TYPE = "wallbox_type"                    # "e3dc" | "generic"
CONF_WALLBOX_SERVICE_ON = "wallbox_service_on"
CONF_WALLBOX_SERVICE_OFF = "wallbox_service_off"
CONF_WALLBOX_CURRENT_SENSOR = "wallbox_current_sensor"
CONF_WALLBOX_MIN_CURRENT = "wallbox_min_current"      # A
CONF_WALLBOX_MAX_CURRENT = "wallbox_max_current"      # A
CONF_WALLBOX_PHASES = "wallbox_phases"                # 1 or 3
CONF_WALLBOX_MIN_SURPLUS = "wallbox_min_surplus"      # W

# Wallbox power source (separater Verbrauchszähler)
# Trennt EV-Ladeverbrauch vom Hausverbrauch, damit Optimizer/EWMA/Forecast
# nicht durch Ladespitzen verfälscht werden.
CONF_WALLBOX_PROVIDER = "wallbox_provider"                  # none|e3dc|openwb|custom (UI-Hinweis)
CONF_WALLBOX_POWER_SENSOR = "wallbox_power_sensor"          # entity_id, W
CONF_WALLBOX_INCLUDED_IN_HOUSE = "wallbox_included_in_house"  # bool: True = Hausverbrauchszähler enthält Wallbox bereits

# Config entry keys – heat pump (Step 7)
CONF_HP_ENABLED = "hp_enabled"
CONF_HP_SWITCH_ENTITY = "hp_switch_entity"
CONF_HP_SERVICE_ON = "hp_service_on"
CONF_HP_SERVICE_OFF = "hp_service_off"
CONF_HP_MIN_SURPLUS = "hp_min_surplus"                # W
CONF_HP_MAX_PRICE = "hp_max_price"                    # €/kWh
CONF_HP_TIME_START = "hp_time_start"                  # HH:MM
CONF_HP_TIME_END = "hp_time_end"                      # HH:MM
CONF_HP_MIN_RUN_MINUTES = "hp_min_run_minutes"
CONF_HP_MIN_PAUSE_MINUTES = "hp_min_pause_minutes"

# Config entry keys – PV forecast (charge delay)
CONF_PV_FORECAST_ENABLED = "pv_forecast_enabled"
CONF_PV_FORECAST_SENSOR = "pv_forecast_sensor"        # entity_id, value = remaining kWh today
CONF_PV_FORECAST_SENSOR_DAY2 = "pv_forecast_sensor_day2"  # optional: hourly forecast for tomorrow (Solcast: prognose_morgen)
CONF_PV_FORECAST_THRESHOLD_KWH = "pv_forecast_threshold_kwh"  # min remaining kWh to delay
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"    # usable capacity for sizing
CONF_PV_FORECAST_SAFETY_FACTOR = "pv_forecast_safety_factor"  # forecast_remaining >= required * factor
CONF_DELAY_MIN_SOC = "delay_min_soc"                  # % SoC; below this floor pv_delay/astro_wait must not block charging

# Config entry keys – Schwacher-PV-Tag (Akku-Priorität an bewölkten Tagen)
CONF_PV_FORECAST_TODAY_SENSOR = "pv_forecast_today_sensor"  # entity_id, value = Tagessumme heute (kWh)
CONF_LOW_YIELD_PRIORITY_ENABLED = "low_yield_priority_enabled"  # bool
CONF_LOW_YIELD_THRESHOLD = "low_yield_threshold"                # 0–1; ≤ Schwelle → schwacher Tag
CONF_LOW_YIELD_REFERENCE_KWH = "low_yield_reference_kwh"        # kWh, 0 = automatisch
CONF_LOW_YIELD_REFERENCE_KWH_PER_KWP = "low_yield_reference_kwh_per_kwp"  # kWh/kWp Faktor
DEFAULT_LOW_YIELD_PRIORITY_ENABLED = True
DEFAULT_LOW_YIELD_THRESHOLD = 0.5
DEFAULT_LOW_YIELD_REFERENCE_KWH = 0.0
DEFAULT_LOW_YIELD_REFERENCE_KWH_PER_KWP = 5.5
# Low-Yield: Lade-Limit nur ändern wenn Überschuss um mehr als X W schwankt
# Config entry keys – F1+: Vorausschauende Ladung (Forward-Looking)
# Hebt das Ladeziel intelligent an, wenn morgen wenig PV erwartet wird,
# damit heutiger Überschuss in den Akku statt ins Netz fließt.
CONF_FORWARD_LOOKING_ENABLED = "forward_looking_enabled"           # bool
CONF_TOMORROW_PV_SENSOR = "tomorrow_pv_sensor"                     # entity_id, value = morgen PV in kWh
CONF_FORWARD_LOOKING_MAX_SOC = "forward_looking_max_soc"           # % – Obergrenze für dynamisches Ziel
DEFAULT_FORWARD_LOOKING_ENABLED = False
DEFAULT_FORWARD_LOOKING_MAX_SOC = 100.0

# Config entry keys – SoC hysteresis + charge ramp (A1/A2)
CONF_SOC_HYSTERESIS_PERCENT = "soc_hysteresis_percent"  # % – dead-band to suppress SoC noise
CONF_CHARGE_RAMP_W_PER_CYCLE = "charge_ramp_w_per_cycle"  # W – max step per control cycle

# Config entry keys – seasonal emergency reserve (B1)
CONF_SEASONAL_RESERVE_ENABLED = "seasonal_reserve_enabled"  # bool
CONF_RESERVE_WINTER_PERCENT = "reserve_winter_percent"       # % SoC at winter solstice
CONF_RESERVE_EQUINOX_PERCENT = "reserve_equinox_percent"     # % SoC at equinox

# Config entry keys – Phase D: verbrauchsadaptive Reserven
CONF_ADAPTIVE_RESERVE_ENABLED = "adaptive_reserve_enabled"            # bool
CONF_ADAPTIVE_RESERVE_LOOKBACK_DAYS = "adaptive_reserve_lookback_days"  # days
CONF_ADAPTIVE_RESERVE_MIN_DAYS = "adaptive_reserve_min_days"          # required days
CONF_ADAPTIVE_RESERVE_SAFETY_FACTOR = "adaptive_reserve_safety_factor"  # multiplier
CONF_ADAPTIVE_RESERVE_MIN_SOC = "adaptive_reserve_min_soc"            # % floor
CONF_ADAPTIVE_RESERVE_MAX_SOC = "adaptive_reserve_max_soc"            # % cap

# Config entry keys – spreading / Ladeverteilung (E2)
CONF_SPREADING_ENABLED = "spreading_enabled"        # bool
CONF_SPREADING_TARGET_SOC = "spreading_target_soc"  # % SoC, default 100

# Config entry keys – curtailment guard (E3/Phase 1)
CONF_CURTAILMENT_GUARD_ENABLED = "curtailment_guard_enabled"  # bool
CONF_CURTAILMENT_ACTIVATION_W = "curtailment_activation_w"   # W – hysteresis on-threshold
CONF_CURTAILMENT_RELEASE_W = "curtailment_release_w"         # W – hysteresis off-threshold

# Config entry keys – lower-corridor pause (Phase 2)
CONF_LOWER_CORRIDOR_PAUSE_ENABLED = "lower_corridor_pause_enabled"  # bool

# Config entry keys – Two-Tier Ladeende (Phase 4)
CONF_TWO_TIER_ENABLED = "two_tier_enabled"            # bool
CONF_CHARGE_TARGET_LATE = "charge_target_late"        # % SoC – spätes Ziel (z.B. 95 %)
CONF_LATE_CHARGE_END_H = "late_charge_end_h"          # Stunde – Ende Spät-Ladezeit (z.B. 20.0)

# Config entry keys – Morning Pre-Discharge (Phase 6 / Plan Phase 3)
CONF_MORNING_DISCHARGE_MODE = "morning_discharge_mode"           # off | passive | active_house | active_grid
CONF_MORNING_UNLOAD_SOC = "morning_unload_soc"                   # % SoC Entlade-Ziel (default 40)
CONF_MORNING_UNLOAD_START_SOC = "morning_unload_start_soc"       # % SoC Einschalt-Schwelle (default 60)
CONF_PRE_DISCHARGE_OFFSET_H = "pre_discharge_offset_h"           # Stunden vor Ladeende-Start (default 4)
CONF_PRE_DISCHARGE_MAX_POWER_W = "pre_discharge_max_power_w"     # W max. Entladeleistung (default 2000)
CONF_PRE_DISCHARGE_SAFETY_FACTOR = "pre_discharge_safety_factor" # Prognose-Sicherheitsfaktor (default 1.3)
CONF_PRE_DISCHARGE_TIBBER_AUTO = "pre_discharge_tibber_auto"     # bool: Tibber-gesteuerte Auto-Hochstufung
CONF_MORNING_GRID_EXPORT_THRESHOLD = "morning_grid_export_threshold"  # €/kWh – Preis für active_grid-Hochstufung

# Manual force-discharge (dashboard switch)
CONF_FORCE_DISCHARGE_POWER_W = "force_discharge_power_w"          # W Entladeleistung bei manueller Erzwingung (default 3000)
DEFAULT_FORCE_DISCHARGE_POWER_W = 3000

# Morning discharge mode choices
MORNING_DISCHARGE_OFF = "off"
MORNING_DISCHARGE_PASSIVE = "passive"
MORNING_DISCHARGE_ACTIVE_HOUSE = "active_house"
MORNING_DISCHARGE_ACTIVE_GRID = "active_grid"

# Config entry keys – EVCC integration (D1)
CONF_EVCC_ENABLED = "evcc_enabled"                  # bool
CONF_EVCC_CHARGING_ENTITY = "evcc_charging_entity"  # entity_id (boolean/binary_sensor)
CONF_EVCC_MODE_ENTITY = "evcc_mode_entity"          # entity_id (string state: "now", "pv", …)
CONF_EVCC_NOW_VALUE = "evcc_now_value"              # state-Wert der als 'Now' gilt (z. B. "sofortladen")
CONF_EVCC_DISCHARGE_LIMIT_W = "evcc_discharge_limit_w"  # max Entladeleistung bei EVCC Now-Modus (W, 0 = sperren)

# Config entry keys – failsafes (Step 8)
CONF_WATCHDOG_TIMEOUT = "watchdog_timeout"            # minutes, 0 = disabled

# Wallbox type choices
WALLBOX_TYPE_E3DC = "e3dc"
WALLBOX_TYPE_GENERIC = "generic"

# Wallbox power-source provider choices (UI-Hint, wirkt nur in config_flow)
WALLBOX_PROVIDER_NONE = "none"
WALLBOX_PROVIDER_E3DC = "e3dc"
WALLBOX_PROVIDER_OPENWB = "openwb"
WALLBOX_PROVIDER_CUSTOM = "custom"
WALLBOX_PROVIDERS = [
    WALLBOX_PROVIDER_NONE,
    WALLBOX_PROVIDER_E3DC,
    WALLBOX_PROVIDER_OPENWB,
    WALLBOX_PROVIDER_CUSTOM,
]
DEFAULT_WALLBOX_PROVIDER = WALLBOX_PROVIDER_NONE
# E3DC: eigener Powermeter → NICHT im Hausverbrauch enthalten (Default False)
# openWB: hängt am EVU-Hauptzähler → Default True
DEFAULT_WALLBOX_INCLUDED_IN_HOUSE = False

# Control phases (states of the phase sensor)
PHASE_OFF = "off"
PHASE_MANUAL = "manual"
PHASE_EMERGENCY = "emergency"                    # SoC < charge_threshold
PHASE_FEED_IN_LIMIT = "feed_in_limit"            # Einspeisedrosselung
PHASE_RESERVE_PROTECTION = "reserve_protection"  # Saisonale Notstromreserve (B1)
PHASE_EVCC_PAUSE = "evcc_pause"                  # EVCC lädt im Now-Modus (D1)
PHASE_HT_PROTECTION = "ht_protection"            # Hochtarif-Schutz
PHASE_CORRIDOR = "corridor"                      # saisonaler Ladekorridor
PHASE_PV_DELAY = "pv_delay"                      # Ladeverzögerung wegen guter PV-Prognose
PHASE_MORNING_DISCHARGE = "morning_discharge"    # Morgen-Vorentladung (Phase 3/6)
PHASE_SPREADING = "spreading"                    # zeitbasierte Ladeverteilung (E2)
PHASE_CURTAILMENT_GUARD = "curtailment_guard"    # Abregelschutz aktiv (E3/Phase 1)
PHASE_ASTRO_WAIT = "astro_wait"                  # Warten auf Sonne (Phase 7)
PHASE_MORNING_CAP = "morning_cap"                # F0: Morning-SoC-Cap aktiv
PHASE_HARD_SOC_LIMIT = "hard_soc_limit"          # G0: Fester Max-SoC-Deckel (Akku-Schonung)
PHASE_FAST_FLOOR = "fast_floor"                  # Schnelllade-Boden: voller PV-Überschuss bis Floor-SoC
PHASE_FORCE_DISCHARGE = "force_discharge"        # manueller Schalter im Dashboard
PHASE_IDLE = "idle"                              # kein Bedarf

# ── Anti-flapping: feed-in-limit hysteresis ───────────────────────────────────
# Neue Aktivierung erst ab diesem Überschuss (W) oberhalb des Limits.
# Verhindert, dass reines Messrauschen (z.B. 4–150 W) die Phase triggert.
FEED_IN_TRIGGER_EXCESS_W: float = 150.0
# Phase wird gehalten solange excess > dieser Schwelle (0 = sofortiger Abbruch).
FEED_IN_RELEASE_EXCESS_W: float = 0.0
# Sekunden, in denen pv_delay nach feed_in_limit unterdrückt wird (Anti-Pendeln).
FEED_IN_PV_DELAY_COOLDOWN_S: float = 60.0

# ── Anti-flapping: EWMA-Glättung der Leistungswerte ──────────────────────────
# Zeitkonstante τ [s] für Exponential-Weighted-Moving-Average auf PV/Last.
EWMA_TAU_S: float = 60.0
# Sprünge > dieser Schwelle [W] setzen den EWMA sofort zurück (z.B. Wallbox-Start).
EWMA_JUMP_THRESHOLD_W: float = 2000.0

ALL_PHASES = [
    PHASE_OFF,
    PHASE_MANUAL,
    PHASE_EMERGENCY,
    PHASE_FEED_IN_LIMIT,
    PHASE_RESERVE_PROTECTION,
    PHASE_EVCC_PAUSE,
    PHASE_HT_PROTECTION,
    PHASE_FORCE_DISCHARGE,
    PHASE_MORNING_DISCHARGE,
    PHASE_ASTRO_WAIT,
    PHASE_MORNING_CAP,
    PHASE_HARD_SOC_LIMIT,
    PHASE_FAST_FLOOR,
    PHASE_CORRIDOR,
    PHASE_PV_DELAY,
    PHASE_SPREADING,
    PHASE_CURTAILMENT_GUARD,
    PHASE_IDLE,
]

# Default values
DEFAULT_INVERTER_POWER = 12000
DEFAULT_MAX_CHARGE_POWER = 3000
DEFAULT_MIN_CHARGE_POWER = 300
DEFAULT_FEED_IN_LIMIT_PERCENT = 70.0
DEFAULT_INSTALLED_KWP = 10.0
DEFAULT_CHARGE_THRESHOLD = 15
DEFAULT_CHARGE_TARGET = 85
DEFAULT_WINTER_MINIMUM_HOUR = 11
DEFAULT_SUMMER_MAXIMUM_HOUR = 14
DEFAULT_SUMMER_CHARGE_END = 18.5
DEFAULT_HT_ON = 5
DEFAULT_HT_OFF = 21
DEFAULT_HT_MIN = 50
DEFAULT_HT_SOCKEL = 10
DEFAULT_CHEAP_THRESHOLD = 0.10
DEFAULT_MAX_GRID_CHARGE_KWH = 3.0
DEFAULT_WALLBOX_MIN_CURRENT = 6
DEFAULT_WALLBOX_MAX_CURRENT = 16
DEFAULT_WALLBOX_PHASES = "3"  # SelectSelector erwartet str (options=["1","3"])
DEFAULT_WALLBOX_MIN_SURPLUS = 1400
DEFAULT_HP_MIN_SURPLUS = 2000
DEFAULT_HP_MAX_PRICE = 0.15
DEFAULT_HP_MIN_RUN_MINUTES = 20
DEFAULT_HP_MIN_PAUSE_MINUTES = 15
DEFAULT_WATCHDOG_TIMEOUT = 10
DEFAULT_UPDATE_INTERVAL = 30
DEFAULT_LOWER_CORRIDOR = 500
DEFAULT_UPPER_CORRIDOR = 1500
DEFAULT_PV_FORECAST_THRESHOLD_KWH = 5.0
DEFAULT_BATTERY_CAPACITY_KWH = 10.0
DEFAULT_PV_FORECAST_SAFETY_FACTOR = 1.2
DEFAULT_DELAY_MIN_SOC = 0.0  # 0 = Floor deaktiviert (altes Verhalten)
DEFAULT_FAST_CHARGE_FLOOR_ENABLED = False
DEFAULT_FAST_CHARGE_FLOOR_SOC = 40.0
DEFAULT_SOC_HYSTERESIS_PERCENT = 2.0
DEFAULT_CHARGE_RAMP_W_PER_CYCLE = 200
DEFAULT_RESERVE_WINTER_PERCENT = 30
DEFAULT_RESERVE_EQUINOX_PERCENT = 15
DEFAULT_ADAPTIVE_RESERVE_ENABLED = False
DEFAULT_ADAPTIVE_RESERVE_LOOKBACK_DAYS = 14
DEFAULT_ADAPTIVE_RESERVE_MIN_DAYS = 7
DEFAULT_ADAPTIVE_RESERVE_SAFETY_FACTOR = 1.3
DEFAULT_ADAPTIVE_RESERVE_MIN_SOC = 5.0
DEFAULT_ADAPTIVE_RESERVE_MAX_SOC = 35.0
DEFAULT_EVCC_NOW_VALUE = "now"  # openWB: "Instant Charging"
DEFAULT_EVCC_DISCHARGE_LIMIT_W = 0  # 0 = Entladung vollständig sperren
DEFAULT_SPREADING_TARGET_SOC = 100.0
DEFAULT_CURTAILMENT_GUARD_ENABLED = True
DEFAULT_CURTAILMENT_ACTIVATION_W = 1500  # W above which guard activates
DEFAULT_CURTAILMENT_RELEASE_W = 500      # W below which guard deactivates
DEFAULT_LOWER_CORRIDOR_PAUSE_ENABLED = True
DEFAULT_TWO_TIER_ENABLED = False
DEFAULT_CHARGE_TARGET_LATE = 95.0
DEFAULT_LATE_CHARGE_END_H = 20.0
DEFAULT_MORNING_DISCHARGE_MODE = "off"
DEFAULT_MORNING_UNLOAD_SOC = 40.0
DEFAULT_MORNING_UNLOAD_START_SOC = 60.0
DEFAULT_PRE_DISCHARGE_OFFSET_H = 4.0
DEFAULT_PRE_DISCHARGE_MAX_POWER_W = 2000
DEFAULT_PRE_DISCHARGE_SAFETY_FACTOR = 1.3
DEFAULT_PRE_DISCHARGE_TIBBER_AUTO = False
DEFAULT_MORNING_GRID_EXPORT_THRESHOLD = 0.15

# Phase 7: Astro-Modus
CONF_ASTRO_ENABLED = "astro_enabled"
CONF_ASTRO_LATITUDE = "astro_latitude"
CONF_ASTRO_LONGITUDE = "astro_longitude"
CONF_CHARGE_END_SUNSET_OFFSET_H = "charge_end_sunset_offset_h"
CONF_CHARGE_START_SUNRISE_OFFSET_H = "charge_start_sunrise_offset_h"
DEFAULT_ASTRO_ENABLED = False
DEFAULT_ASTRO_LATITUDE = 48.0
DEFAULT_ASTRO_LONGITUDE = 11.0
DEFAULT_CHARGE_END_SUNSET_OFFSET_H = -2.0   # 2h vor Sonnenuntergang
DEFAULT_CHARGE_START_SUNRISE_OFFSET_H = 2.0  # 2h nach Sonnenaufgang

# F0: Flat-Curve / Morning-Cap + Gentle-Charge
CONF_MORNING_CAP_ENABLED = "morning_cap_enabled"           # bool
CONF_MORNING_CAP_SOC = "morning_cap_soc"                   # % SoC ceiling until cap_until_h
CONF_MORNING_CAP_UNTIL_H = "morning_cap_until_h"           # hour local time (HA tz), e.g. 10.0
CONF_GENTLE_CHARGE_ENABLED = "gentle_charge_enabled"       # bool
CONF_GENTLE_CHARGE_FACTOR = "gentle_charge_factor"         # 0.1–1.0 multiplier
DEFAULT_MORNING_CAP_ENABLED = False
DEFAULT_MORNING_CAP_SOC = 30.0
DEFAULT_MORNING_CAP_UNTIL_H = 9.0
DEFAULT_GENTLE_CHARGE_ENABLED = False
DEFAULT_GENTLE_CHARGE_FACTOR = 0.35

# G0: Hard SoC Limit (Akku-Schonung mit Curtailment-Bypass)
CONF_HARD_SOC_LIMIT_ENABLED = "hard_soc_limit_enabled"   # bool
CONF_HARD_SOC_LIMIT = "hard_soc_limit"                   # % SoC absoluter Deckel
DEFAULT_HARD_SOC_LIMIT_ENABLED = False
DEFAULT_HARD_SOC_LIMIT = 80.0

# F3: Auto-Optimierungs-Modus
CONF_AUTO_MODE_ENABLED = "auto_mode_enabled"               # bool
CONF_AUTO_MODE_OBJECTIVE = "auto_mode_objective"           # self_consumption | cost | co2
DEFAULT_AUTO_MODE_ENABLED = False
DEFAULT_AUTO_MODE_OBJECTIVE = "self_consumption"
AUTO_MODE_OBJECTIVES = ["self_consumption", "cost", "co2"]

# Tariff mode + cost tracking (v0.2.0)
# tariff_mode steuert, ob Strategien aktiviert werden dürfen, die Netzenergie
# in den Akku einspeisen (Forward-Looking, gentle_charge bei TARIFF_LOW, …).
#  - "fixed":   Fester Tarif → Netzladung kategorisch verboten (außer Notfall,
#               Feed-in-Limit-Schutz, Curtailment-Guard)
#  - "dynamic": Dynamischer Tarif → Netzladung bei TARIFF_LOW erlaubt
CONF_TARIFF_MODE = "tariff_mode"
CONF_FIXED_BUY_PRICE = "fixed_buy_price"        # €/kWh Strombezug bei festem Tarif
CONF_FEED_IN_PRICE = "feed_in_price"            # €/kWh Einspeisevergütung
CONF_BATTERY_CAPEX_EUR = "battery_capex_eur"    # € Anschaffungskosten Speicher (für Wear-Cost)
CONF_BATTERY_TOTAL_CYCLES = "battery_total_cycles"  # Lebensdauer-Vollzyklen lt. Hersteller

TARIFF_MODE_FIXED = "fixed"
TARIFF_MODE_DYNAMIC = "dynamic"
TARIFF_MODES = [TARIFF_MODE_FIXED, TARIFF_MODE_DYNAMIC]

DEFAULT_TARIFF_MODE = TARIFF_MODE_FIXED
DEFAULT_FIXED_BUY_PRICE = 0.30
DEFAULT_FEED_IN_PRICE = 0.08
DEFAULT_BATTERY_CAPEX_EUR = 8000.0
DEFAULT_BATTERY_TOTAL_CYCLES = 5000.0

# Untergrenze, ab der "unjustified_grid_charge" anschlägt (kWh/Tag).
# Verhindert False-Positives durch winzige Mess-Restbeiträge.
UNJUSTIFIED_GRID_CHARGE_THRESHOLD_KWH = 0.5

# Manual charge rate-limit
MANUAL_CHARGE_MIN_INTERVAL_HOURS = 2

# Coordinator data keys
DATA_SOC = "soc"
DATA_PV_POWER = "pv_power"
DATA_HOUSE_POWER = "house_power"
DATA_GRID_POWER = "grid_power"
DATA_BATTERY_POWER = "battery_power"
DATA_WALLBOX_POWER = "wallbox_power"

# Statistics keys
STAT_CHARGED_TODAY = "charged_today_kwh"
STAT_DISCHARGED_TODAY = "discharged_today_kwh"
STAT_FEED_IN_INTERVENTIONS = "feed_in_interventions_today"
STAT_CURTAILMENT_AVOIDED = "curtailment_avoided_today_kwh"
STAT_FEED_IN_AVOIDED = "feed_in_avoided_today_kwh"
STAT_PV_SAVED = "pv_saved_today_kwh"
# v0.2.0: cost tracking + sanity check
STAT_GRID_DRAW_TODAY = "grid_draw_today_kwh"          # kWh aus dem Netz bezogen
STAT_GRID_FEED_IN_TODAY = "grid_feed_in_today_kwh"    # kWh ins Netz eingespeist
STAT_GRID_TO_BATTERY_TODAY = "grid_to_battery_today_kwh"  # kWh Netz → Akku (Sanity)
STAT_BATTERY_THROUGHPUT_TODAY = "battery_throughput_today_kwh"  # für Wear-Cost
# v0.3.0: zeitvariable €-Akkumulation + Eigenverbrauch + Verschleiß
STAT_COST_TODAY_EUR = "cost_today_eur"                # Bezugskosten heute (€), zeitvariabel
STAT_FEED_IN_REVENUE_TODAY_EUR = "feed_in_revenue_today_eur"  # Einspeise-Erlös heute (€)
STAT_PV_SELF_CONSUMPTION_TODAY = "pv_self_consumption_today_kwh"  # PV direkt → Haus (kWh)
STAT_PV_SAVINGS_TODAY_EUR = "pv_savings_today_eur"   # vermiedener Bezug durch PV (€)
STAT_BATTERY_WEAR_TODAY_EUR = "battery_wear_today_eur"  # Akku-Verschleiß heute (€)
# Wallbox-Energieverbrauch separat (kWh, total_increasing)
STAT_WALLBOX_ENERGY_TODAY = "wallbox_energy_today_kwh"

# ── Battery & PV Sizing Advisor ──────────────────────────────────────────────

# Config entry keys – sizing advisor step
CONF_SIZING_PV_ENERGY_SENSOR = "sizing_pv_energy_sensor"
CONF_SIZING_HOUSE_ENERGY_SENSOR = "sizing_house_energy_sensor"
CONF_SIZING_HOUSE_FROM_BALANCE = "sizing_house_from_balance"
DEFAULT_SIZING_HOUSE_FROM_BALANCE = False
# Volatile toggle – never persisted. When set at save-time the sizing sensors
# are re-imported from the HA Energy Dashboard, overwriting stored values.
CONF_SIZING_IMPORT_FROM_ENERGY_DASHBOARD = "sizing_import_from_energy_dashboard"
CONF_SIZING_GRID_IMPORT_ENERGY_SENSOR = "sizing_grid_import_energy_sensor"
CONF_SIZING_GRID_EXPORT_ENERGY_SENSOR = "sizing_grid_export_energy_sensor"
CONF_SIZING_BATTERY_CHARGE_ENERGY_SENSOR = "sizing_battery_charge_energy_sensor"
CONF_SIZING_BATTERY_DISCHARGE_ENERGY_SENSOR = "sizing_battery_discharge_energy_sensor"
CONF_SIZING_WALLBOX_ENERGY_SENSOR = "sizing_wallbox_energy_sensor"        # optional
CONF_SIZING_HEAT_PUMP_ENERGY_SENSOR = "sizing_heat_pump_energy_sensor"    # optional
CONF_SIZING_ANALYSIS_DAYS = "sizing_analysis_days"
CONF_SIZING_ELECTRICITY_PRICE_EUR_KWH = "sizing_electricity_price_eur_kwh"
CONF_SIZING_FEED_IN_PRICE_EUR_KWH = "sizing_feed_in_price_eur_kwh"
CONF_SIZING_BATTERY_PRICE_EUR_KWH = "sizing_battery_price_eur_kwh"
CONF_SIZING_PV_PRICE_EUR_PER_KWP = "sizing_pv_price_eur_per_kwp"
CONF_SIZING_INVERTER_UPGRADE_PRICE_EUR = "sizing_inverter_upgrade_price_eur"
CONF_SIZING_ROUND_TRIP_EFFICIENCY = "sizing_round_trip_efficiency"
CONF_SIZING_MAX_BATTERY_SWEEP_KWH = "sizing_max_battery_sweep_kwh"
CONF_SIZING_BATTERY_STEP_KWH = "sizing_battery_step_kwh"
CONF_SIZING_MAX_PV_EXPANSION_KWP = "sizing_max_pv_expansion_kwp"
CONF_SIZING_PV_STEP_KWP = "sizing_pv_step_kwp"

# Defaults – sizing advisor
DEFAULT_SIZING_ANALYSIS_DAYS = 365
DEFAULT_SIZING_ELECTRICITY_PRICE = 0.30        # €/kWh
DEFAULT_SIZING_FEED_IN_PRICE = 0.08            # €/kWh
DEFAULT_SIZING_BATTERY_PRICE_EUR_KWH = 600.0   # €/kWh usable capacity
DEFAULT_SIZING_PV_PRICE_EUR_PER_KWP = 1200.0   # €/kWp installed
DEFAULT_SIZING_INVERTER_UPGRADE_PRICE_EUR = 1500.0  # € lump sum when WR upgrade needed
DEFAULT_SIZING_ROUND_TRIP_EFFICIENCY = 0.92    # round-trip (charge × discharge)
DEFAULT_SIZING_MAX_BATTERY_SWEEP_KWH = 30.0
DEFAULT_SIZING_BATTERY_STEP_KWH = 2.5
DEFAULT_SIZING_MAX_PV_EXPANSION_KWP = 20.0
DEFAULT_SIZING_PV_STEP_KWP = 2.0

# Simulation constants
SIZING_C_RATE = 0.5   # max charge/discharge per hour as fraction of capacity (0.5 C)
# WR upgrade is triggered when (installed_kwp + extra_kwp) exceeds inverter_kw by this factor
SIZING_INVERTER_UPGRADE_THRESHOLD = 1.2
# Max battery lifetime in years for payback viability check
SIZING_MAX_PAYBACK_YEARS = 15.0
