"""How long the firmware has been running, from a monotonic source.

Diagnosing a wedged Pico means telling "running for a week" from "rebooted
thirty seconds ago", and neither the logs nor the wall clock can say: the RTC
starts unset and only gets a value if Wi-Fi came up and `set_time()` ran, which
is exactly the path that fails when you need this.

So the clock here is `time.ticks_ms()`, which counts from boot regardless. It
wraps — 2**30 ms is about twelve and a half days, well inside the uptimes this
is meant to report — so the elapsed time is accumulated from `ticks_diff`
deltas rather than subtracted from a start value. Sampling more often than the
wrap period is the only requirement, and /status or a display tick manages that
by a wide margin.

No MicroPython-only imports, so it can be tested under CPython — the same
reason `pico/timeutil.py` and `pico/textutil.py` sit apart from `utils`.
"""

import time

# MicroPython's ticks counter wraps at this period; ticks_diff knows it, and
# the fallback below has to use the same modulus to behave identically.
_TICKS_PERIOD = 1 << 30
_TICKS_HALF = _TICKS_PERIOD // 2


def _ticks_ms():
    """Milliseconds since boot, wrapping — MicroPython's, or an equivalent."""
    fn = getattr(time, "ticks_ms", None)
    if fn is not None:
        return fn()
    # CPython: monotonic() does not wrap, so it is folded into the same period
    # to keep both runtimes on one code path.
    return int(time.monotonic() * 1000) % _TICKS_PERIOD


def _ticks_diff(new, old):
    fn = getattr(time, "ticks_diff", None)
    if fn is not None:
        return fn(new, old)
    # Same signed-wrap semantics as MicroPython's: the result is the shortest
    # distance between the two, which is negative if `new` precedes `old`.
    return (new - old + _TICKS_HALF) % _TICKS_PERIOD - _TICKS_HALF


class Uptime:
    """Accumulates elapsed milliseconds across ticks wraparound.

    `ticks` is injectable so the tests can drive the counter over a wrap
    without waiting twelve days for one.
    """

    def __init__(self, ticks=_ticks_ms):
        self._ticks = ticks
        self._last = ticks()
        self._elapsed_ms = 0

    def _sample(self):
        now = self._ticks()
        delta = _ticks_diff(now, self._last)
        # A negative delta means the counter went backwards, which it cannot do
        # in real time: treat it as zero rather than letting uptime shrink.
        if delta > 0:
            self._elapsed_ms += delta
        self._last = now
        return self._elapsed_ms

    def seconds(self):
        """Whole seconds since boot. Raw number, for the JSON status."""
        return self._sample() // 1000

    def human(self):
        """`3d 4h 12m 7s`, for a human reading a log line."""
        return format_uptime(self.seconds())


def format_uptime(seconds):
    """Seconds to the largest three units that are non-zero.

    Days are kept even at 0h so `9d 0h 0m` does not read as nine minutes, and
    seconds are dropped once there are days — nobody diagnosing a week of
    uptime cares about the seconds, and the line is narrower without them.
    """
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return "%dd %dh %dm" % (days, hours, minutes)
    if hours:
        return "%dh %dm %ds" % (hours, minutes, secs)
    if minutes:
        return "%dm %ds" % (minutes, secs)
    return "%ds" % secs


# The one the firmware uses. Constructed at import, which is as close to boot as
# a module can get — main.py imports it before the network comes up.
UPTIME = Uptime()
