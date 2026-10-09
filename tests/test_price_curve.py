"""Tests für die Preiskurven-Extraktion (Nordpool/Tibber/aWATTar-Formate)."""
from __future__ import annotations

import datetime as dt

from custom_components.e3dc_maestro.price_curve import (
    build_horizon,
    extract_price_slots,
    read_price_horizon,
)

TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 10, 9, 18, 20, tzinfo=TZ)


def _raw(day: int, prices: list[float], step_h: float = 1.0) -> list[dict]:
    base = dt.datetime(2026, 10, day, tzinfo=TZ)
    out = []
    for i, p in enumerate(prices):
        s = base + dt.timedelta(hours=i * step_h)
        e = s + dt.timedelta(hours=step_h)
        out.append({"start": s.isoformat(), "end": e.isoformat(), "value": p})
    return out


class TestExtract:
    def test_raw_today_tomorrow(self):
        attrs = {"raw_today": _raw(9, [0.3] * 24), "raw_tomorrow": _raw(10, [0.2] * 24)}
        slots = extract_price_slots(attrs, NOW)
        assert len(slots) == 48
        assert slots[0].hours == 1.0

    def test_float_lists_hourly(self):
        attrs = {"today": [0.1 * i for i in range(24)], "tomorrow": [0.5] * 24}
        slots = extract_price_slots(attrs, NOW)
        assert len(slots) == 48
        assert slots[18].start == dt.datetime(2026, 10, 9, 18, tzinfo=TZ)
        assert abs(slots[18].price - 1.8) < 1e-9
        assert slots[24].start.day == 10

    def test_float_lists_quarter_hour(self):
        slots = extract_price_slots({"today": [0.3] * 96}, NOW)
        assert len(slots) == 96
        assert slots[1].hours == 0.25

    def test_none_entries_are_skipped(self):
        slots = extract_price_slots({"today": [0.3] * 23 + [None]}, NOW)
        assert len(slots) == 23

    def test_tibber_style_prices(self):
        attrs = {"prices": [
            {"startsAt": "2026-10-09T18:00:00+02:00", "total": 0.31},
            {"startsAt": "2026-10-09T19:00:00+02:00", "total": 0.35},
        ]}
        slots = extract_price_slots(attrs, NOW)
        assert [s.price for s in slots] == [0.31, 0.35]
        assert slots[0].hours == 1.0 and slots[1].hours == 1.0

    def test_epoch_ms_timestamps_and_naive_strings(self):
        ts = int(dt.datetime(2026, 10, 9, 18, tzinfo=TZ).timestamp() * 1000)
        slots = extract_price_slots({"data": [{"start": ts, "price": 0.3}]}, NOW)
        assert slots[0].start == dt.datetime(2026, 10, 9, 18, tzinfo=TZ)
        slots = extract_price_slots({"data": [{"start": "2026-10-09T18:00:00", "price": 0.3}]}, NOW)
        assert slots[0].start.utcoffset() == dt.timedelta(hours=2)

    def test_offset_without_colon(self):
        """aWATTar-Simulationssensor liefert '+0200' (strftime %z)."""
        attrs = {"raw_today": [
            {"start": "2026-10-09T18:00:00+0200", "end": "2026-10-09T19:00:00+0200", "value": 0.2963},
        ]}
        slots = extract_price_slots(attrs, NOW)
        assert slots[0].start == dt.datetime(2026, 10, 9, 18, tzinfo=TZ)
        assert slots[0].hours == 1.0

    def test_garbage_is_ignored(self):
        assert extract_price_slots({}, NOW) == []
        assert extract_price_slots({"raw_today": "x", "today": [1, 2, 3]}, NOW) == []
        assert extract_price_slots({"raw_today": [{"start": "bad", "value": "x"}]}, NOW) == []

    def test_dict_data_wins_over_float_lists(self):
        attrs = {"raw_today": _raw(9, [0.3] * 24), "today": [9.9] * 24}
        assert all(s.price == 0.3 for s in extract_price_slots(attrs, NOW))


class TestHorizon:
    def test_first_slot_is_truncated_to_now(self):
        h = read_price_horizon({"raw_today": _raw(9, [0.3] * 24)}, NOW)
        assert h is not None
        assert abs(h.slot_hours[0] - 40 / 60) < 1e-9  # 18:20 → 19:00
        assert len(h.prices) == 6  # until midnight

    def test_runs_into_tomorrow(self):
        attrs = {"raw_today": _raw(9, [0.3] * 24), "raw_tomorrow": _raw(10, [0.2] * 24)}
        h = read_price_horizon(attrs, NOW)
        assert h is not None
        assert h.known_until == dt.datetime(2026, 10, 11, 0, tzinfo=TZ)
        assert abs(h.total_hours - (29 + 40 / 60)) < 1e-9

    def test_max_hours_caps_horizon(self):
        attrs = {"raw_today": _raw(9, [0.3] * 24), "raw_tomorrow": _raw(10, [0.2] * 24)}
        h = read_price_horizon(attrs, NOW, max_hours=12)
        assert h is not None
        assert abs(h.total_hours - 12) < 1e-9

    def test_gap_stops_horizon(self):
        today = _raw(9, [0.3] * 24)
        del today[21]  # 21:00 fehlt
        h = read_price_horizon({"raw_today": today}, NOW)
        assert h is not None
        assert h.known_until == dt.datetime(2026, 10, 9, 21, tzinfo=TZ)

    def test_now_outside_known_slots(self):
        late = dt.datetime(2026, 10, 12, 12, tzinfo=TZ)
        assert read_price_horizon({"raw_today": _raw(9, [0.3] * 24)}, late) is None

    def test_mixed_resolution(self):
        attrs = {"raw_today": _raw(9, [0.3] * 96, step_h=0.25)}
        h = read_price_horizon(attrs, NOW)
        assert h is not None
        assert abs(h.slot_hours[0] - 10 / 60) < 1e-9  # 18:20 → 18:30
        assert build_horizon([], NOW) is None
