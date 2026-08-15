"""Carbon Intensity API payload handling.

`pico/ci_api_parse.py` deliberately has no MicroPython-only imports so this
runs under CPython — the reason it lives apart from `pico/providers/ci_api.py`.

The two cases worth guarding are the ones the API's own README warns about: a
zone reading carries no consumption figures, and nothing in the response says
whether it is stale, so the client has to work that out itself.
"""

import importlib.util
import pathlib

# Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow
# the standard library's `http` package and break every other test in the run.
_spec = importlib.util.spec_from_file_location(
    "pico_ci_api_parse",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "ci_api_parse.py",
)
_parse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parse)

MAX_AGE_SEC = _parse.MAX_AGE_SEC
freshness_error = _parse.freshness_error
pick_intensity = _parse.pick_intensity
reading_path = _parse.reading_path

NOW = 1_755_000_000

COUNTRY_PAYLOAD = {
    "country": "Italy",
    "country_code": "IT",
    "basis": "measured",
    "unit": "gCO2eq/kWh",
    "direct": 274,
    "lifecycle": 319,
    "consumption_direct": 339,
    "consumption_lifecycle": 384,
}

ZONE_PAYLOAD = {
    "country_code": "IT",
    "zone": "SICI",
    "basis": "measured",
    "direct": 411,
    "lifecycle": 456,
}


def test_country_and_zone_paths():
    assert reading_path("it") == "/v1/last-hour/IT"
    assert reading_path("IT", "sici") == "/v1/zones/IT/SICI"


def test_reports_consumption_lifecycle_for_a_country():
    assert pick_intensity(COUNTRY_PAYLOAD) == (384.0, "consumption_lifecycle")


def test_falls_back_to_lifecycle_for_a_zone():
    # Zones omit both consumption figures; the import adjustment is national.
    assert pick_intensity(ZONE_PAYLOAD) == (456.0, "lifecycle")


def test_no_figure_at_all_is_reported_as_missing():
    assert pick_intensity({"basis": "measured"}) == (None, None)


def test_fresh_measurement_passes():
    assert freshness_error(COUNTRY_PAYLOAD, NOW - 600, NOW) is None


def test_annual_average_is_rejected():
    # A yearly constant in an hourly reading's shape: stored as samples it
    # draws a flat line and every hour scores the same.
    annual = dict(COUNTRY_PAYLOAD, basis="annual-average", hour_start=None)
    assert freshness_error(annual, NOW - 60, NOW) is not None


def test_missed_pipeline_run_is_rejected():
    assert freshness_error(COUNTRY_PAYLOAD, NOW - MAX_AGE_SEC - 1, NOW) is not None
    assert freshness_error(COUNTRY_PAYLOAD, NOW - MAX_AGE_SEC + 1, NOW) is None


def test_unparsable_generated_at_is_rejected():
    assert freshness_error(COUNTRY_PAYLOAD, None, NOW) is not None
