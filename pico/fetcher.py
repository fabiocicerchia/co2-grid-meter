"""Provider I/O on its own thread, so a slow provider cannot stall the device.

WHY THIS EXISTS: fetching, rendering and serving all ran on one loop. A
provider that took twenty seconds to answer took the e-ink refresh and `/` with
it — the device looked hung, and the one number it exists to show was the thing
that had stopped updating. Tighter per-provider timeouts cap that stall; they
do not remove it, because the request still waits for the timeout.

The shape is stale-while-revalidate, not a thread pool. The request path never
performs I/O: it reads the last published value, and if that value is older than
the TTL it asks the worker to refresh. The worker is the only code that touches
the network.

Three properties matter more than throughput on a Pico:

  * A FETCH FAILURE NEVER REPLACES A GOOD READING. The worker builds the whole
    new value and publishes it with one rebind under the lock, so a half-built
    dict is never visible, and an exception leaves the previous reading in
    place. That is the "half-written reading on screen" this is meant to stop.
  * ONE FETCH IN FLIGHT. Requests arriving while a fetch runs coalesce onto it
    rather than starting a second. RAM is the budget on this device, and two
    provider responses resident at once is how it runs out.
  * BOUNDED MEMORY. Window keys carry a time range, so a new key appears every
    hour and nothing ever asks for the old one again. Only the most recent few
    are kept — the same trap TtlCache had to grow a sweep for.

`_thread` is what MicroPython ships (one extra thread on the RP2040's second
core). CPython's `_thread` has the same three calls used here, so the tests run
the real code rather than a simulation of it.
"""

import _thread
import time


def _log(message):
    """Log through utils when it is importable.

    Deliberately lazy: utils pulls in MicroPython's ujson and network modules,
    and this module is otherwise pure enough to run under CPython unmodified —
    which is what lets the tests exercise the real threading rather than a
    stand-in for it.
    """
    try:
        from utils import log
    except ImportError:
        return
    log(message)


# How many published keys to keep. The window key moves every hour and the
# status key is stable, so a handful covers "current" plus the overlay and a
# little history for a device whose clock has just jumped.
MAX_PUBLISHED = 8

# How long a request waits for the very first value. A device that answers
# "no data" for the whole of its first fetch reads as broken; one that pauses
# briefly on the first call and is instant afterwards reads as starting up.
COLD_WAIT_SECONDS = 20

# The worker's idle poll. Long enough not to burn the second core, short enough
# that a refresh request is not visibly delayed.
POLL_SECONDS = 0.2


class BackgroundFetcher:
    """Last-known-good values, refreshed off the request path.

    `factory` callables are supplied per key by the caller, exactly as
    `TtlCache.get_or_set` takes them, so this is a drop-in for it.
    """

    def __init__(
        self,
        ttl_seconds,
        cold_wait_seconds=COLD_WAIT_SECONDS,
        time_fn=None,
        sleep_fn=None,
        log_fn=None,
    ):
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.cold_wait_seconds = max(0, int(cold_wait_seconds))
        self._time = time_fn or time.time
        self._sleep = sleep_fn or time.sleep
        self._log = log_fn or _log
        self._lock = _thread.allocate_lock()
        # key -> (published_at, value). Only ever replaced wholesale.
        self._published = {}
        # The single job slot. Latest request wins; an identical one coalesces.
        self._pending = None
        self._running = False
        self._busy = False
        self.fetches = 0
        self.failures = 0
        self.last_error = None

    # ---- request side -----------------------------------------------------

    def get_or_set(self, key, factory):
        """The freshest value available for `key`, without blocking on I/O.

        Returns None only when nothing has ever been fetched for this key and
        the first fetch did not finish inside `cold_wait_seconds` — the caller
        renders "warming up" rather than a wrong number.
        """
        published_at, value = self.published(key)
        now = self._time()

        if value is not None:
            if now - published_at >= self.ttl_seconds:
                self._request(key, factory)
                self._drain_if_no_worker()
            return value

        # Cold: ask, then wait a bounded time for the first answer.
        self._request(key, factory)
        if self._drain_if_no_worker():
            return self.published(key)[1]
        deadline = now + self.cold_wait_seconds
        while self._time() < deadline:
            _, value = self.published(key)
            if value is not None:
                return value
            self._sleep(POLL_SECONDS)
        return None

    def published(self, key):
        """(published_at, value) for a key, or (0, None) if never published.

        The timestamp is the identity of a reading: the display uses a change
        in it to decide when a full e-ink clear is warranted, which is not the
        same question as "did this call do the fetching".
        """
        with self._lock:
            item = self._published.get(key)
        return item if item else (0, None)

    def age_of(self, key):
        """Seconds since this key was published, or None if it never was."""
        published_at, value = self.published(key)
        return None if value is None else self._time() - published_at

    def stats(self):
        with self._lock:
            return {
                "running": self._running,
                "busy": self._busy,
                "published": len(self._published),
                "fetches": self.fetches,
                "failures": self.failures,
                "last_error": self.last_error,
            }

    # ---- worker side ------------------------------------------------------

    def start(self):
        """Run the worker on the second core. Idempotent."""
        with self._lock:
            if self._running:
                return False
            self._running = True
        try:
            _thread.start_new_thread(self._loop, ())
        except Exception as error:
            # A device that cannot spawn the thread must still serve. The
            # caller falls back to fetching inline — slow, but not dead.
            with self._lock:
                self._running = False
            self._log("Fetcher thread unavailable: %s" % error)
            return False
        return True

    def stop(self):
        with self._lock:
            self._running = False

    def _loop(self):
        while True:
            with self._lock:
                if not self._running:
                    return
            if not self.drain_once():
                self._sleep(POLL_SECONDS)

    def drain_once(self):
        """Run one pending job, if there is one. True when work was done.

        Public so the tests can drive the worker without a thread — the
        threading is what makes this useful on the device, not what makes it
        correct.
        """
        with self._lock:
            job = self._pending
            self._pending = None
            if job is None:
                return False
            self._busy = True

        key, factory = job
        try:
            value = factory()
            self.fetches += 1
            # One rebind, under the lock, of a value that is already complete.
            with self._lock:
                self._published[key] = (self._time(), value)
                self._sweep()
        except Exception as error:
            # The previous reading stays exactly as it was.
            self.failures += 1
            self.last_error = str(error)
            self._log("Background fetch failed: %s" % error)
        finally:
            with self._lock:
                self._busy = False
        return True

    # ---- internals --------------------------------------------------------

    def _drain_if_no_worker(self):
        """Fetch inline when there is no worker thread. True when it ran.

        A Pico that cannot start the second thread — or a caller that never
        called start() — has to keep serving. This is the old synchronous
        behaviour, kept as the fallback rather than as the design.
        """
        with self._lock:
            running = self._running
        if running:
            return False
        return self.drain_once()

    def _request(self, key, factory):
        with self._lock:
            # Coalesce: an identical outstanding request is already the job.
            if self._pending is not None and self._pending[0] == key:
                return
            self._pending = (key, factory)

    def _sweep(self):
        """Keep only the most recently published keys. Caller holds the lock."""
        if len(self._published) <= MAX_PUBLISHED:
            return
        by_age = sorted(self._published.items(), key=lambda kv: kv[1][0])
        for key, _ in by_age[: len(self._published) - MAX_PUBLISHED]:
            del self._published[key]
