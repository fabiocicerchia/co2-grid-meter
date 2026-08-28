"""Carbon Intensity API v2 payload handling.

`pico/ci_api_parse.py` deliberately has no MicroPython-only imports so this
runs under CPython — the reason it lives apart from `pico/providers/ci_api.py`.

The cases worth guarding are the ones that corrupt a timeline silently: a null
hour that shifts every later value if it is compacted away, a zone document
with no consumption arrays, and a window whose newest hour is too old to
describe now.
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
day_starts = _parse.day_starts
day_values = _parse.day_values
history_path = _parse.history_path
hour_points = _parse.hour_points
stale_error = _parse.stale_error

# 2026-08-27T00:00:00Z, so the arithmetic below reads as clock hours.
MIDNIGHT = 1_787_788_800
NOW = MIDNIGHT + 3 * 3600

COUNTRY_DAY = {
    "country_code": "IT",
    "zone": "IT",
    "basis": "measured",
    "date": "2026-08-27",
    "start": "2026-08-27T00:00:00Z",
    "step_sec": 3600,
    "direct": [297, None, 292],
    "lifecycle": [342, None, 337],
    "consumption_direct": [362, None, 357],
    "consumption_lifecycle": [407, None, 402],
}

ZONE_DAY = {
    "country_code": "IT",
    "zone": "SICI",
    "basis": "measured",
    "start": "2026-08-27T00:00:00Z",
    "step_sec": 3600,
    "direct": [411, 405, None],
    "lifecycle": [456, 450, None],
}


def test_country_and_zone_paths():
    assert history_path("it", "2026-08-27") == "/v2/IT/history/2026-08-27"
    assert history_path("IT", "2026-08-27", "sici") == "/v2/IT/SICI/history/2026-08-27"


def test_reports_consumption_lifecycle_for_a_country():
    values, figure = day_values(COUNTRY_DAY)
    assert figure == "consumption_lifecycle"
    assert values == [407, None, 402]


def test_falls_back_to_lifecycle_for_a_zone():
    # Zones omit both consumption arrays; the import adjustment is national.
    assert day_values(ZONE_DAY)[1] == "lifecycle"


def test_annual_average_is_rejected():
    # A yearly constant in an hourly document's shape: drawn as a timeline it
    # is a flat line and every hour scores the same.
    assert day_values(dict(COUNTRY_DAY, basis="annual-average")) == ([], None)


def test_a_day_of_only_nulls_has_no_figure():
    assert day_values(dict(COUNTRY_DAY, **{k: [None] for k in _parse.FIGURES}))[0] == []


def test_an_unexpected_step_is_refused_not_guessed():
    # Nothing downstream carries a step, so a 1800s document would file every
    # value under the wrong hour.
    assert day_values(dict(COUNTRY_DAY, step_sec=1800)) == ([], None)


def test_a_null_hour_keeps_the_hours_after_it_in_place():
    # The whole point of the columnar form: index is the hour.
    assert hour_points([407, None, 402], MIDNIGHT) == [
        (MIDNIGHT, 407.0),
        (MIDNIGHT + 2 * 3600, 402.0),
    ]


def test_no_values_is_no_points():
    assert hour_points([], MIDNIGHT) == []
    assert hour_points([407], None) == []


def test_window_covers_the_day_on_each_side_of_midnight():
    assert day_starts(MIDNIGHT - 1800, MIDNIGHT + 1800) == [
        MIDNIGHT - 86400,
        MIDNIGHT,
    ]
    assert day_starts(MIDNIGHT, MIDNIGHT) == [MIDNIGHT]


def test_fresh_hour_passes():
    assert stale_error(NOW - 600, NOW) is None


def test_missed_pipeline_run_is_rejected():
    assert stale_error(NOW - MAX_AGE_SEC - 1, NOW) is not None
    assert stale_error(NOW - MAX_AGE_SEC + 1, NOW) is None


def test_an_empty_window_is_rejected():
    assert stale_error(None, NOW) is not None
