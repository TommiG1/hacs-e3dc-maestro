"""Sensor-facing diagnostic properties for E3DC Maestro."""
from __future__ import annotations

import logging
import statistics
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .const import PHASE_PV_DELAY
from .control_engine import (
    active_tariff_slot as _active_tariff_slot,
    adaptive_emergency_reserve_soc as _adaptive_emergency_reserve_soc,
    adaptive_ht_reserve_soc as _adaptive_ht_reserve_soc,
    astro_sunrise_sunset as _astro_sunrise_sunset,
    seasonal_charge_end_hour as _seasonal_charge_end_hour,
    seasonal_reserve_soc as _seasonal_reserve_soc,
    tariff_schedule_from_params as _tariff_schedule_from_params,
)
from .coordinator_helpers import (
    _effective_discharge_limit_w,
    quarter_slot as _quarter_slot,
)

_LOGGER = logging.getLogger(__name__)


class CoordinatorDiagnosticsMixin:
    _AUTONOMY_MIN_SAMPLES = 60  # ~10 min bei 10 s-Polling


    @property
    def avg_house_power_w(self) -> float:
        """Typical house power (W) over the rolling measurement window.

        Liefert den **Median** der absoluten Hausverbrauchswerte – das ist
        robust gegen kurze Lastspitzen (Backofen-Anlauf, WP-Verdichter,
        Wasserkocher), die das arithmetische Mittel über ein 60-min-Fenster
        nach oben verzerren.
        """
        if not self._house_power_window:
            return 0.0
        return statistics.median(abs(v) for v in self._house_power_window)


    @property
    def autonomy_hours(self) -> float | None:
        """Estimated battery autonomy in hours based on current SoC and typical house load."""
        if not self.data or "state" not in self.data:
            return None
        state = self.data["state"]
        # Warm-up-Gate: Solange das Fenster zu kurz ist, ist der Median nicht
        # belastbar (eine 30-s-Spitze würde die Schätzung verzerren). Wir
        # zeigen lieber "unbekannt" als einen unsinnigen Wert.
        if len(self._house_power_window) < self._AUTONOMY_MIN_SAMPLES:
            return None
        avg = self.avg_house_power_w
        if avg < 10:
            # Fallback: aktueller Momentanverbrauch (z. B. wenn der Sensor
            # konstant 0 lieferte und das Window voller Nullen ist).
            current = abs(state.house_power)
            if current < 10:
                current = abs(min(state.battery_power, 0.0))
            if current < 10:
                return None
            avg = current
        soc = state.soc
        kwh_remaining = (soc / 100.0) * self._params.battery_capacity_kwh
        hours = kwh_remaining / (avg / 1000.0)
        return round(min(hours, 999.0), 1)


    @property
    def autonomy_str(self) -> str | None:
        """Autonomy time formatted as 'Xh YYmin'."""
        h = self.autonomy_hours
        if h is None:
            return None
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours}h {minutes:02d}min"


    @property
    def seasonal_reserve_soc(self) -> float | None:
        """Currently active seasonal emergency reserve SoC (%) or None if disabled."""
        if not self._params.seasonal_reserve_enabled:
            return None
        return round(_seasonal_reserve_soc(dt_util.now(), self._params), 1)


    @property
    def adaptive_reserve_soc(self) -> float | None:
        """Currently computed adaptive emergency reserve SoC (%) or None.

        Returns ``None`` when adaptive reserves are disabled or there is not
        yet enough recorder history.
        """
        if not self._params.adaptive_reserve_enabled:
            return None
        if not self.data or "state" not in self.data:
            return None
        value = _adaptive_emergency_reserve_soc(self.data["state"], self._params)
        return round(value, 1) if value is not None else None


    @property
    def adaptive_ht_reserve_soc(self) -> float | None:
        """Currently computed adaptive HT reserve SoC (%) or None."""
        if not self._params.adaptive_reserve_enabled:
            return None
        if not self.data or "state" not in self.data:
            return None
        schedule = _tariff_schedule_from_params(self._params)
        slot = _active_tariff_slot(dt_util.now(), schedule)
        if slot is None:
            for s in schedule.slots:
                if s.class_ == "high":
                    slot = s
                    break
        value = _adaptive_ht_reserve_soc(self.data["state"], self._params, slot)
        return round(value, 1) if value is not None else None


    @property
    def forward_looking_target_soc(self) -> float | None:
        """Aktuell vom Forward-Looking errechnetes dynamisches Ladeziel (%).

        Liefert None wenn das Feature aus ist oder noch keine Werte berechnet
        wurden.
        """
        if not self._params.forward_looking_enabled:
            return None
        return self._fwd_looking_target


    @property
    def tomorrow_pv_kwh(self) -> float | None:
        """Erwarteter PV-Ertrag morgen (kWh) – aus konfiguriertem Sensor."""
        if not self.data or "state" not in self.data:
            return None
        return self.data["state"].tomorrow_pv_kwh


    @property
    def tomorrow_deficit_kwh(self) -> float | None:
        """Erwarteter Energie-Defizit morgen = max(0, consumption - pv) (kWh)."""
        if not self.data or "state" not in self.data:
            return None
        s = self.data["state"]
        if s.tomorrow_pv_kwh is None or s.tomorrow_consumption_kwh is None:
            return None
        return round(max(0.0, s.tomorrow_consumption_kwh - s.tomorrow_pv_kwh), 2)


    def _is_low_yield_day_active(self) -> bool:
        """Schwacher Tag aus gelatchter Prognose + aktuellen Params (Schwelle live)."""
        if not self._params.low_yield_priority_enabled:
            return False
        if self._low_yield_today_kwh is None or self._low_yield_today_kwh < 0:
            return False
        from .control_engine import MaestroState, is_low_yield_day

        probe = MaestroState(
            soc=0,
            pv_power=0,
            house_power=0,
            grid_power=0,
            battery_power=0,
            pv_forecast_today_kwh=self._low_yield_today_kwh,
            pv_stats_peak_kwh=self._low_yield_stats_peak_kwh,
        )
        return is_low_yield_day(
            probe, self._params, stats_peak_kwh=self._low_yield_stats_peak_kwh
        )


    @property
    def low_yield_day_active(self) -> bool:
        """True wenn gelatchte Tagesprognose unter der aktuellen Schwelle liegt."""
        return self._is_low_yield_day_active()


    @property
    def low_yield_today_kwh(self) -> float | None:
        """Aktuelle Tagesprognose (kWh), wie sie für die Latch-Auswertung genutzt wurde."""
        return self._low_yield_today_kwh


    @property
    def low_yield_reference_kwh(self) -> float | None:
        """Berechnete Referenz (kWh) aus kWp-Baseline, Statistik und Override."""
        from .control_engine import reference_pv_yield_kwh
        ref = reference_pv_yield_kwh(
            self._params, stats_peak_kwh=self._low_yield_stats_peak_kwh
        )
        return round(ref, 2) if ref > 0 else None


    @property
    def low_yield_ratio(self) -> float | None:
        """Verhältnis Tagesprognose / Referenz (0–1+) oder None."""
        ref = self.low_yield_reference_kwh
        if ref is None or ref <= 0 or self._low_yield_today_kwh is None:
            return None
        return round(self._low_yield_today_kwh / ref, 3)


    @property
    def last_sent_charge_limit(self) -> int | None:
        """Lade-Cap in Watt, das zuletzt per e3dc_rscp gesendet wurde.

        Unterscheidet sich vom Soll (``last_decision.charge_power_limit``):
        Der Soll-Wert wird in jedem Zyklus neu berechnet, aber nur bei
        ausreichender Drift (Debounce) tatsächlich an die E3DC übertragen.
        """
        return self._last_sent_charge_limit


    @property
    def last_sent_discharge_limit(self) -> int | None:
        """Entlade-Cap in Watt, das zuletzt per e3dc_rscp gesendet wurde."""
        return self._last_sent_discharge_limit


    @property
    def effective_discharge_limit(self) -> int | None:
        """Soll-Entlade-Cap inkl. implizit freier Entladung (WR-Nennleistung)."""
        if self.last_decision is None:
            return None
        return _effective_discharge_limit_w(
            self.last_decision, self._params.max_charge_power
        )


    @property
    def seasonal_charge_end_h(self) -> float:
        """Currently computed seasonal charge-end hour (fractional, local time)."""
        return round(_seasonal_charge_end_hour(dt_util.now(), self._params), 2)


    @property
    def seasonal_charge_end_str(self) -> str:
        """Seasonal charge-end formatted as HH:MM string."""
        h = _seasonal_charge_end_hour(dt_util.now(), self._params)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"


    @property
    def astro_charge_start_h(self) -> float | None:
        """Heute berechneter Ladestart (Sonnenaufgang + Offset), nur bei Astro-Modus.

        Liefert None wenn der Astro-Modus deaktiviert ist – dann gibt es
        keinen astronomisch berechneten Ladestart, das Gate aus
        ``charge_start_sunrise_offset_h`` ist inaktiv.
        """
        if not self._params.astro_enabled:
            return None
        sunrise_h, _ = _astro_sunrise_sunset(dt_util.now(), self._params)
        return round(sunrise_h + self._params.charge_start_sunrise_offset_h, 2)


    @property
    def astro_charge_start_str(self) -> str | None:
        """Heutiger astronomischer Ladestart als HH:MM, sonst None."""
        h = self.astro_charge_start_h
        if h is None:
            return None
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"


    @property
    def tomorrow_charge_end_str(self) -> str:
        """Voraussichtliches Ladeende morgen als HH:MM (gleiche Logik wie heute, +1 Tag)."""
        tomorrow = dt_util.now() + timedelta(days=1)
        h = _seasonal_charge_end_hour(tomorrow, self._params)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"


    @property
    def pv_delay_charge_start_str(self) -> str | None:
        """Voraussichtlicher Ladestart bei aktiver PV-Verzögerung als HH:MM.

        Liefert None, wenn die aktuelle Phase nicht ``pv_delay`` ist oder
        keine Forecast-Trajektorie vorliegt. Andernfalls wird die erste
        Stunde aus ``forecast.trajectory_phases`` zurückgegeben, in der
        Maestro nicht mehr verzögert. Findet sich in den nächsten 24 h
        keine andere Phase, fällt das Ergebnis auf das saisonale Ladeende
        zurück (späteste Reserveladung).
        """
        if self.last_decision is None or self.last_decision.phase != PHASE_PV_DELAY:
            return None
        now = dt_util.now()
        # Default-Fallback: saisonales Ladeende (späteste Reserve-Ladung)
        fallback_h = _seasonal_charge_end_hour(now, self._params)
        target_h: float | None = None
        if self.forecast is not None and self.forecast.trajectory_phases:
            # Trajectory is quarter-hour (15 min) when len≈96, else hourly.
            n = len(self.forecast.trajectory_phases)
            step_minutes = 15 if n >= 96 else 60
            base = _quarter_slot(now) if step_minutes == 15 else now.replace(
                minute=0, second=0, microsecond=0
            )
            for i, phase in enumerate(self.forecast.trajectory_phases):
                if phase != PHASE_PV_DELAY:
                    ts = base + timedelta(minutes=step_minutes * (i + 1))
                    target_h = ts.hour + ts.minute / 60
                    break
        if target_h is None:
            target_h = fallback_h
        hours = int(target_h)
        minutes = round((target_h - hours) * 60)
        if minutes == 60:
            hours = (hours + 1) % 24
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"


    @property
    def tomorrow_charge_start_str(self) -> str | None:
        """Voraussichtlicher Ladestart morgen als HH:MM (nur bei Astro-Modus), sonst None."""
        if not self._params.astro_enabled:
            return None
        tomorrow = dt_util.now() + timedelta(days=1)
        sunrise_h, _ = _astro_sunrise_sunset(tomorrow, self._params)
        h = round(sunrise_h + self._params.charge_start_sunrise_offset_h, 2)
        hours = int(h)
        minutes = round((h - hours) * 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"
