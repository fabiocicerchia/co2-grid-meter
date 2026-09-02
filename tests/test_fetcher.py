"""The background fetcher: a slow provider must not stall the request path.

Loaded by path, NOT by putting pico/ on sys.path for the session: pico/http.py
would shadow the stdlib http package. Same pattern as test_export.py.
"""

import importlib.util
import pathlib
import sys
import threading
import time

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


def _load():
    sys.path.insert(0, str(PICO))
    try:
        spec = importlib.util.spec_from_file_location(
            "pico_fetcher", PICO / "fetcher.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["pico_fetcher"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PICO))


fetcher = _load()
BackgroundFetcher = fetcher.BackgroundFetcher


@pytest.fixture
def clock():
    """A clock the test moves by hand, so TTL expiry is not a sleep."""

    class Clock:
        def __init__(self):
            self.t = 1000.0

        def time(self):
            return self.t

        def sleep(self, seconds):
            self.t += seconds

    return Clock()


def make(clock, **kw):
    kw.setdefault("ttl_seconds", 60)
    kw.setdefault("time_fn", clock.time)
    kw.setdefault("sleep_fn", clock.sleep)
    kw.setdefault("log_fn", lambda *_: None)
    return BackgroundFetcher(**kw)


# --- the reason this exists -------------------------------------------------


def test_a_slow_provider_does_not_stall_the_request_path():
    """The whole point. One provider takes a second; the request that follows
    it returns the previous reading immediately rather than waiting."""
    release = threading.Event()
    calls = []

    def slow():
        calls.append(1)
        release.wait(5)
        return {"carbonIntensity": len(calls)}

    f = BackgroundFetcher(ttl_seconds=0, cold_wait_seconds=5, log_fn=lambda *_: None)
    assert f.start()
    try:
        # Cold: this one does wait, briefly, for the first reading.
        release.set()
        assert f.get_or_set(("w",), slow)["carbonIntensity"] == 1

        # Now make the provider hang, and time a request through it.
        release.clear()
        started = time.monotonic()
        value = f.get_or_set(("w",), slow)
        elapsed = time.monotonic() - started

        assert value["carbonIntensity"] == 1, "served the last good reading"
        assert elapsed < 0.5, "the request waited for the provider (%.2fs)" % elapsed
    finally:
        release.set()
        f.stop()


def test_a_failed_fetch_never_replaces_a_good_reading(clock):
    f = make(clock)
    f.get_or_set(("w",), lambda: {"carbonIntensity": 120})
    assert f.published(("w",))[1] == {"carbonIntensity": 120}

    def boom():
        raise OSError("provider timed out")

    clock.t += 999  # stale, so the next call asks for a refresh
    assert f.get_or_set(("w",), boom) == {"carbonIntensity": 120}
    f.drain_once()
    assert f.published(("w",))[1] == {"carbonIntensity": 120}
    assert f.stats()["failures"] == 1
    assert "timed out" in f.stats()["last_error"]


def test_a_reading_is_published_whole_or_not_at_all(clock):
    """Half a reading on screen is the failure mode; the value is built before
    the lock is taken and swapped in with one rebind."""
    f = make(clock)
    f.get_or_set(("w",), lambda: {"history": [1, 2, 3]})
    first = f.published(("w",))[1]

    clock.t += 999

    def partial():
        first["history"] = []  # a factory that mutates the published value
        raise ValueError("died halfway")

    f.get_or_set(("w",), partial)
    f.drain_once()
    # The published object is the one the caller was handed; the guarantee is
    # that a *failed* fetch publishes nothing, not that callers cannot scribble
    # on what they were given.
    assert f.stats()["failures"] == 1
    assert f.published(("w",))[1] is first


# --- the mechanics ----------------------------------------------------------


def test_a_fresh_value_is_served_without_asking_for_a_refresh(clock):
    calls = []
    f = make(clock, ttl_seconds=60)
    f.get_or_set(("w",), lambda: calls.append(1) or "v1")
    assert len(calls) == 1

    clock.t += 30  # still inside the TTL
    assert f.get_or_set(("w",), lambda: calls.append(1) or "v2") == "v1"
    f.drain_once()
    assert len(calls) == 1, "a fresh value must not trigger a fetch"


def test_a_stale_value_is_served_and_refreshed_behind_it(clock):
    f = make(clock, ttl_seconds=60)
    f.get_or_set(("w",), lambda: "v1")
    clock.t += 61
    # Stale: the old value comes back now, the new one lands afterwards.
    assert f.get_or_set(("w",), lambda: "v2") == "v1"
    f.drain_once()
    assert f.published(("w",))[1] == "v2"


def test_requests_for_the_same_key_coalesce_onto_one_fetch(clock):
    calls = []

    def slow():
        calls.append(1)
        return "v"

    f = make(clock, ttl_seconds=0)
    f.start = lambda: False  # no worker; drive it by hand
    f._request(("w",), slow)
    f._request(("w",), slow)
    f._request(("w",), slow)
    f.drain_once()
    assert len(calls) == 1
    assert f.drain_once() is False, "three requests, one job"


def test_published_keys_are_bounded(clock):
    f = make(clock, ttl_seconds=0)
    for i in range(fetcher.MAX_PUBLISHED + 5):
        clock.t += 1
        f.get_or_set(("w", i), lambda i=i: i)
    assert f.stats()["published"] == fetcher.MAX_PUBLISHED
    # The oldest went, the newest stayed.
    assert f.published(("w", 0))[1] is None
    assert f.published(("w", fetcher.MAX_PUBLISHED + 4))[1] == fetcher.MAX_PUBLISHED + 4


def test_a_cold_key_gives_up_rather_than_waiting_forever(clock):
    """No worker, and the inline fallback disabled: the caller gets None and
    renders "warming up" instead of blocking the loop."""
    f = make(clock, ttl_seconds=60, cold_wait_seconds=2)
    f._drain_if_no_worker = lambda: False
    assert f.get_or_set(("w",), lambda: "v") is None


def test_without_a_worker_it_still_fetches_inline(clock):
    """A Pico that cannot start the second thread has to keep working."""
    f = make(clock)
    assert f.stats()["running"] is False
    assert f.get_or_set(("w",), lambda: "v") == "v"


def test_the_publish_timestamp_moves_only_when_a_reading_lands(clock):
    """app.py uses this to decide when a full e-ink clear is warranted."""
    f = make(clock, ttl_seconds=60)
    f.get_or_set(("w",), lambda: "v1")
    stamp = f.published(("w",))[0]

    clock.t += 10
    f.get_or_set(("w",), lambda: "v2")  # fresh — no fetch
    assert f.published(("w",))[0] == stamp

    clock.t += 60
    f.get_or_set(("w",), lambda: "v2")
    f.drain_once()
    assert f.published(("w",))[0] > stamp


def test_start_is_idempotent():
    f = BackgroundFetcher(ttl_seconds=60, log_fn=lambda *_: None)
    try:
        assert f.start() is True
        assert f.start() is False, "a second worker would double the RAM cost"
    finally:
        f.stop()
