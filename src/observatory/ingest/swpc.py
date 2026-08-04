"""Collector for NOAA SWPC space-weather feeds.

Physics background
------------------
L1 (the first Sun-Earth Lagrange point) is a gravitationally stable spot
~1.5 million km from Earth toward the Sun. The DSCOVR satellite (with ACE
as automatic fallback) sits there and samples the solar wind *before* it
reaches Earth — the wind takes another ~30-60 minutes to arrive, which is
exactly the warning time that makes space-weather forecasting possible.

Metrics we store:
- sw_speed / sw_density — solar wind proton speed (km/s) and density
  (protons/cm3) measured at L1; faster/denser wind hits the magnetosphere
  harder.
- bz — the north-south component of the interplanetary magnetic field at
  L1 (GSM frame, nT). The key trigger: southward (negative) Bz "opens" the
  magnetosphere and lets solar wind energy pour in -> geomagnetic storms
  and auroras. Northward Bz keeps it mostly closed.
- kp — planetary geomagnetic activity index (0-9, 3-hour intervals),
  averaged from 13 ground magnetometers worldwide. This is the *effect* on
  Earth, whereas the L1 metrics are the *cause* arriving ahead of it.

Endpoints (all list-of-dicts format):
1. Planetary K-index — 3-hourly.
2. RTSW solar wind plasma — 1-minute L1 measurements of proton speed
   and density.
3. RTSW interplanetary magnetic field — 1-minute L1 measurements,
   we keep the GSM Bz component.

RTSW = Real-Time Solar Wind: raw (pre-propagation) L1 measurements.
We deliberately avoid NOAA's propagated-solar-wind product: those values
already ran through NOAA's propagation model, and training our Phase 3
aurora model on them would leak part of the prediction target into the
features. Raw L1 in, observed Kp out — a clean cause/effect pair.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from observatory.infra.http import get_json
from observatory.infra.logging_setup import setup_logging
from observatory.repository import SpaceWeatherMeasurement, insert_measurements

logger = logging.getLogger(__name__)

ENDPOINTS = {
    "kp": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "rtsw_wind": "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
    "rtsw_mag": "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json",
}


def _parse_noaa_timestamp(raw: str) -> datetime:
    """Parse a NOAA time_tag as UTC-aware datetime.

    NOAA emits ISO-8601 strings, sometimes with a Z suffix and sometimes
    without a timezone at all. Python 3.11+ ``fromisoformat`` handles both.
    Naive datetimes are labelled UTC since NOAA data is always UTC.
    """
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_noaa_dict_list(
    data: list[dict[str, Any]],
    field_name: str,
    metric_name: str,
) -> list[SpaceWeatherMeasurement]:
    """Extract one metric from a list-of-dicts NOAA response.

    Rows with null/missing/unparseable values in the target field are
    silently skipped.
    """
    measurements: list[SpaceWeatherMeasurement] = []
    for row in data:
        try:
            raw_value = row.get(field_name)
            if raw_value is None or raw_value == "":
                continue
            value = float(raw_value)
            ts = _parse_noaa_timestamp(row["time_tag"])
        except (ValueError, TypeError, KeyError):
            continue
        measurements.append(SpaceWeatherMeasurement(ts=ts, metric=metric_name, value=value))
    return measurements


def fetch_kp() -> list[SpaceWeatherMeasurement]:
    """Fetch the planetary K-index endpoint. Returns 'kp' measurements."""
    data = get_json(ENDPOINTS["kp"])
    if data is None:
        return []
    return _parse_noaa_dict_list(data, field_name="Kp", metric_name="kp")


def fetch_rtsw_wind() -> list[SpaceWeatherMeasurement]:
    """Fetch raw L1 solar wind plasma. Returns sw_speed and sw_density."""
    data = get_json(ENDPOINTS["rtsw_wind"])
    if data is None:
        return []
    speeds = _parse_noaa_dict_list(data, field_name="proton_speed", metric_name="sw_speed")
    densities = _parse_noaa_dict_list(data, field_name="proton_density", metric_name="sw_density")
    return speeds + densities


def fetch_rtsw_mag() -> list[SpaceWeatherMeasurement]:
    """Fetch raw L1 interplanetary magnetic field. Returns 'bz' (GSM Bz)."""
    data = get_json(ENDPOINTS["rtsw_mag"])
    if data is None:
        return []
    return _parse_noaa_dict_list(data, field_name="bz_gsm", metric_name="bz")


def fetch_all_space_weather() -> dict[str, int]:
    """Fetch all three NOAA endpoints and insert measurements.

    Errors on one endpoint do not stop the others. Returns dict of endpoint
    name -> count of newly inserted rows.
    """
    counts: dict[str, int] = {}
    fetchers = [
        ("kp", fetch_kp),
        ("rtsw_wind", fetch_rtsw_wind),
        ("rtsw_mag", fetch_rtsw_mag),
    ]
    for source, fetch in fetchers:
        try:
            measurements = fetch()
            inserted = insert_measurements(measurements)
            logger.info(
                "SWPC %s: %d new / %d parsed", source, inserted, len(measurements)
            )
            counts[source] = inserted
        except Exception:
            logger.exception("Unexpected error fetching SWPC %s", source)
            counts[source] = 0
    return counts


def main() -> int:
    setup_logging()
    counts = fetch_all_space_weather()
    total = sum(counts.values())
    print()
    print("New measurements per source:")
    for source, n in counts.items():
        print(f"  {source:12s} {n}")
    print()
    print(f"Total new: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
