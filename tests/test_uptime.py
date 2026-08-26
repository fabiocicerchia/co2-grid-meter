"""Uptime tracking.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.

The interesting case is the wraparound. MicroPython's ticks counter wraps every
~12.4 days, which is well inside the uptimes this exists to report, so the tests
drive a fake counter across the boundary rather than trusting the arithmetic by
inspection.
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "pico_uptime",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "uptime.py",
)
_uptime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_uptime)

Uptime = _uptime.Uptime
format_uptime = _uptime.format_uptime
PERIOD = _uptime._TICKS_PERIOD


class FakeTicks:
    """A ticks_ms() that wraps exactly as MicroPython's does."""

    def __init__(self, start=0):
        self.value = start % PERIOD

    def advance(self, ms):
        self.value = (self.value + ms) % PERIOD

    def __call__(self):
        return self.value


def test_starts_at_zero():
    assert Uptime(FakeTicks()).seconds() == 0


def test_counts_elapsed_time():
    ticks = FakeTicks()
    up = Uptime(ticks)
    ticks.advance(90_000)
    assert up.seconds() == 90


def test_accumulates_across_several_samples():
    ticks = FakeTicks()
    up = Uptime(ticks)
    for _ in range(5):
        ticks.advance(60_000)
        up.seconds()
    assert up.seconds() == 300


def test_survives_the_ticks_wraparound():
    # Start just before the wrap, then step over it. A naive
    # now - start would go hugely negative here.
    ticks = FakeTicks(PERIOD - 5_000)
    up = Uptime(ticks)
    ticks.advance(10_000)  # crosses the boundary
    assert up.seconds() == 10


def test_survives_many_wraps_when_sampled_regularly():
    ticks = FakeTicks()
    up = Uptime(ticks)
    step = PERIOD // 4  # comfortably inside the wrap period
    for _ in range(12):  # three full wraps
        ticks.advance(step)
        up.seconds()
    assert up.seconds() == (12 * step) // 1000


def test_a_counter_going_backwards_does_not_shrink_uptime():
    # Cannot happen on real hardware; if it does, uptime must not go down —
    # a shrinking uptime reads as a reboot that never happened.
    ticks = FakeTicks()
    up = Uptime(ticks)
    ticks.advance(60_000)
    assert up.seconds() == 60
    ticks.value = (ticks.value - 30_000) % PERIOD
    assert up.seconds() == 60


def test_does_not_depend_on_the_wall_clock():
    # No RTC, no set_time(): an unsynced clock must not change the answer.
    ticks = FakeTicks()
    up = Uptime(ticks)
    ticks.advance(3_600_000)
    assert up.seconds() == 3600


class TestFormat:
    def test_seconds_only(self):
        assert format_uptime(45) == "45s"

    def test_minutes_and_seconds(self):
        assert format_uptime(125) == "2m 5s"

    def test_hours_keep_seconds(self):
        assert format_uptime(3725) == "1h 2m 5s"

    def test_days_drop_seconds(self):
        assert format_uptime(3 * 86400 + 4 * 3600 + 12 * 60 + 7) == "3d 4h 12m"

    def test_zero_units_are_kept_once_days_are_shown(self):
        # "9d 0h 0m", not "9m": the largest unit has to lead.
        assert format_uptime(9 * 86400) == "9d 0h 0m"

    def test_zero_and_negative(self):
        assert format_uptime(0) == "0s"
        assert format_uptime(-5) == "0s"
