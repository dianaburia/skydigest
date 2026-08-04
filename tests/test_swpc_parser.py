"""Tests for the NOAA SWPC list-of-dicts response parser."""

from datetime import datetime, timezone

from observatory.ingest.swpc import _parse_noaa_dict_list


KP_FIXTURE = [
    {"time_tag": "2024-01-01T00:00:00", "Kp": 3.33, "station_count": 8},
    {"time_tag": "2024-01-01T03:00:00", "Kp": 4.00, "station_count": 8},
    {"time_tag": "2024-01-01T06:00:00", "Kp": None, "station_count": 8},
]


def test_parses_valid_rows_and_skips_null():
    result = _parse_noaa_dict_list(KP_FIXTURE, "Kp", "kp")
    assert len(result) == 2  # third row has None → skipped
    assert [m.value for m in result] == [3.33, 4.0]
    assert result[0].metric == "kp"
    assert result[0].ts == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_missing_field_skips_all():
    result = _parse_noaa_dict_list(KP_FIXTURE, "nonexistent", "x")
    assert result == []
