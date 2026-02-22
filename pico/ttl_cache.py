"""Tiny TTL cache used by mock server and firmware orchestration."""

from __future__ import annotations

import time


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
