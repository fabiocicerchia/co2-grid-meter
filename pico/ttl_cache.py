"""Tiny TTL cache used by mock server and firmware orchestration."""

# from _future__ import annotations

import time

from utils import log


class TtlCache:
    """Dict-based cache with per-key expiry."""

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._store = {}

    def get(self, key, now=None):
        now = time.time() if now is None else now
        item = self._store.get(key)
        if not item:
            return None

        expires_at, value = item
        if expires_at <= now:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value, now=None):
        now = time.time() if now is None else now
        # ponytail: keys with a moving time-range component (e.g. window
        # start/end) are never re-queried after expiry, so nothing ever pops
        # them via get(). Sweep on write or _store grows unbounded (ENOMEM).
        expired = [k for k, (expires_at, _) in self._store.items() if expires_at <= now]
        for k in expired:
            del self._store[k]
        self._store[key] = (now + self.ttl_seconds, value)
        return value

    def get_or_set(self, key, factory, now=None):
        key_str = " ".join(str(x) for x in key)
        log("Fetching from key '%s'" % key_str)
        cached = self.get(key, now=now)
        if cached is not None:
            log("Key '%s' is cached" % key_str)
            return cached
        log("Key '%s' is not cached" % key_str)
        return self.set(key, factory(), now=now)
