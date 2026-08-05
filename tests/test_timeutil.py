"""EU summer-time rule.

`pico/timeutil.py` deliberately has no MicroPython-only imports so this runs
under CPython — the reason it lives apart from `pico/utils.py`.

Reference instants: EU summer time runs from 01:00 UTC on the last Sunday of
March to 01:00 UTC on the last Sunday of October. Both boundaries are checked
on the minute either side, because "an hour out for seven months" was the
original bug.
"""

import importlib.util
import pathlib

# Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow
# the standard library's `http` package and break every other test in the run.
_spec = importlib.util.spec_from_file_location(
    "pico_timeutil",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "timeutil.py",
)
_timeutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_timeutil)

_day_of_week = _timeutil._day_of_week
_last_sunday = _timeutil._last_sunday
is_eu_summer_time = _timeutil.is_eu_summer_time
utc_offset_seconds = _timeutil.utc_offset_seconds


def test_last_sunday_matches_the_published_changeover_dates():
    # Verifiable against any calendar; these are the actual EU changeover days.
    assert (_last_sunday(2026, 3), _last_sunday(2026, 10)) == (29, 25)
    assert (_last_sunday(2025, 3), _last_sunday(2025, 10)) == (30, 26)
    assert (_last_sunday(2027, 3), _last_sunday(2027, 10)) == (28, 31)


def test_day_of_week_across_a_century_boundary():
    assert _day_of_week(2000, 3, 1) == 3  # Wednesday — 2000 was a leap year
    assert _day_of_week(1900, 3, 1) == 4  # Thursday — 1900 was not
    assert _day_of_week(2026, 3, 29) == 0  # Sunday


def test_spring_forward_happens_at_0100_utc_not_midnight():
    assert not is_eu_summer_time((2026, 3, 29, 0, 59))
    assert is_eu_summer_time((2026, 3, 29, 1, 0))
    # the day before is still winter, whatever the hour
    assert not is_eu_summer_time((2026, 3, 28, 23))


def test_fall_back_happens_at_0100_utc():
    assert is_eu_summer_time((2026, 10, 25, 0, 59))
    assert not is_eu_summer_time((2026, 10, 25, 1, 0))
    assert not is_eu_summer_time((2026, 10, 26, 12))


def test_months_well_inside_each_season():
    assert not is_eu_summer_time((2026, 1, 15, 12))
    assert not is_eu_summer_time((2026, 12, 15, 12))
    assert is_eu_summer_time((2026, 7, 1, 12))
    assert is_eu_summer_time((2026, 5, 20, 3))


def test_offset_is_plus_one_in_winter_and_plus_two_in_summer():
    assert utc_offset_seconds((2026, 1, 15, 12)) == 3600
    assert utc_offset_seconds((2026, 7, 1, 12)) == 7200


def test_a_zone_that_does_not_observe_dst_never_shifts():
    summer = (2026, 7, 1, 12)
    assert utc_offset_seconds(summer, standard_hours=8, observes_dst=False) == 8 * 3600
    # ...and the UK, which does observe it, on the same standard offset as UTC
    assert utc_offset_seconds(summer, standard_hours=0, observes_dst=True) == 3600
