"""Time helpers with no MicroPython-only imports, so they are testable.

`utils.py` pulls in urequests/ujson and cannot be imported under CPython; this
lives apart precisely so the summer-time rule can be unit-tested off-device.
Imported by bare module name (`from timeutil import ...`) to match the flat
filesystem the firmware is flashed onto — see CLAUDE.md.
"""
# Italy (CET/CEST) and the UK (GMT/BST) change at the *same instants*: 01:00 UTC
# on the last Sunday of March and the last Sunday of October. One rule covers
# both, and expressing it in UTC avoids the ambiguity of a local-time rule
# during the hour that repeats.
#
# The day-of-week is computed arithmetically rather than via time.mktime(),
# whose local/UTC interpretation differs between MicroPython and CPython — and
# this code has to give the same answer on the Pico and in the test suite.


def _day_of_week(year, month, day):
    """Sakamoto's algorithm. 0 = Sunday .. 6 = Saturday."""
    table = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    y = year - (1 if month < 3 else 0)
    return (y + y // 4 - y // 100 + y // 400 + table[month - 1] + day) % 7


def _last_sunday(year, month):
    for day in range(31, 24, -1):
        if _day_of_week(year, month, day) == 0:
            return day
    raise ValueError("no Sunday in the last week of %04d-%02d" % (year, month))


def is_eu_summer_time(utc_struct):
    """`time.gmtime()` tuple -> is EU summer time in effect at that UTC instant."""
    year, month, day, hour = (
        utc_struct[0],
        utc_struct[1],
        utc_struct[2],
        utc_struct[3],
    )
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    if month == 3:
        start = _last_sunday(year, 3)
        return day > start or (day == start and hour >= 1)
    end = _last_sunday(year, 10)
    return day < end or (day == end and hour < 1)


def utc_offset_seconds(utc_struct, standard_hours=1, observes_dst=True):
    """Seconds to add to UTC for local wall-clock time."""
    offset = standard_hours * 3600
    if observes_dst and is_eu_summer_time(utc_struct):
        offset += 3600
    return offset
