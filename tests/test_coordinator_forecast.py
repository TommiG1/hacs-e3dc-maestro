"""Unit tests for pure PV forecast profile extraction."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from custom_components.e3dc_maestro.control_engine import MaestroParams
from custom_components.e3dc_maestro.pv_forecast_profile import (
    extract_pv_profile,
    forecast_params_key,
    is_single_day_forecast,
    period_calendar_date,
    unique_calendar_dates_in_attrs,
)


def _halfhour_day(day: date, peak_kw: float = 5.0) -> list[dict]:
    """Build Solcast-like detailedForecast for one local calendar day (CEST)."""
    cest = timezone(timedelta(hours=2))
    items = []
    for h in range(24):
        for minute in (0, 30):
            ts = datetime(day.year, day.month, day.day, h, minute, tzinfo=cest)
            kw = peak_kw if 8 <= h < 18 else 0.0
            items.append({
                "period_start": ts.isoformat(),
                "pv_estimate": kw,
            })
    return items


class TestExtractDetailedForecast:
    def test_prefers_detailed_forecast_30min(self):
        day = date(2026, 7, 19)
        attrs = {"detailedForecast": _halfhour_day(day, peak_kw=4.0)}
        profile = extract_pv_profile(attrs, target_date=day)
        assert profile is not None
        assert len(profile) == 48
        assert max(profile) == 4000.0

    def test_cest_midnight_stays_on_local_day(self):
        """CEST 00:30 must belong to local calendar day, not previous UTC day."""
        day = date(2026, 7, 19)
        cest = timezone(timedelta(hours=2))
        ts = datetime(2026, 7, 19, 0, 30, tzinfo=cest)
        assert period_calendar_date(ts) == day
        assert ts.astimezone(timezone.utc).date() == date(2026, 7, 18)
        attrs = {
            "detailedForecast": [
                {"period_start": ts.isoformat(), "pv_estimate": 0.5},
                {
                    "period_start": datetime(2026, 7, 19, 12, 0, tzinfo=cest).isoformat(),
                    "pv_estimate": 3.0,
                },
            ]
        }
        profile = extract_pv_profile(attrs, target_date=day)
        assert profile is not None
        assert any(v > 0 for v in profile)


class TestIgnoreDateGuard:
    def test_single_day_sensor_allows_ignore_date(self):
        day = date(2026, 7, 20)
        attrs = {"detailedForecast": _halfhour_day(day, peak_kw=2.0)}
        assert is_single_day_forecast(attrs)
        assert extract_pv_profile(attrs, target_date=date(2026, 7, 19)) is None
        profile = extract_pv_profile(
            attrs, target_date=date(2026, 7, 19), ignore_date=True
        )
        assert profile is not None
        assert max(profile) == 2000.0

    def test_multi_day_sensor_not_single_day(self):
        d1 = date(2026, 7, 19)
        d2 = date(2026, 7, 20)
        attrs = {
            "detailedForecast": _halfhour_day(d1, 1.0) + _halfhour_day(d2, 5.0)
        }
        assert not is_single_day_forecast(attrs)
        dates = unique_calendar_dates_in_attrs(attrs)
        assert dates == {d1, d2}
        d1_only = extract_pv_profile(attrs, target_date=d1)
        assert d1_only is not None
        assert max(d1_only) == 1000.0


class TestHourlyShapes:
    def test_plain_24_list(self):
        attrs = {"hourly_wh": [float(i * 100) for i in range(24)]}
        profile = extract_pv_profile(attrs, target_date=date(2026, 7, 19))
        assert profile == [float(i * 100) for i in range(24)]

    def test_watt_hours_dict(self):
        day = date(2026, 7, 19)
        # Use UTC timestamps so bucket index == hour-of-day.
        wh = {
            datetime(2026, 7, 19, h, 0, tzinfo=timezone.utc).isoformat(): float(h * 10)
            for h in range(24)
        }
        attrs = {"watt_hours": wh}
        profile = extract_pv_profile(attrs, target_date=day)
        assert profile is not None
        assert profile[12] == 120.0

    def test_missing_attrs_returns_none(self):
        assert extract_pv_profile({}, target_date=date(2026, 7, 19)) is None


class TestParamsKey:
    def test_fingerprint_changes_with_spreading(self):
        a = MaestroParams(spreading_enabled=True)
        b = MaestroParams(spreading_enabled=False)
        assert forecast_params_key(a) != forecast_params_key(b)
