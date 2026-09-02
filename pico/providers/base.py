import os
import time
from abc import ABC, abstractmethod
from datetime import datetime

import ujson
from utils import (
    ProviderError,
    epoch_to_iso_z,
    floor_hour_epoch,
    log,
    safe_float,
)


def load_json_store(path):
    """A JSON file written by `save_json_store`, or {} if there is none.

    The `.bak` and `.tmp` fallbacks are the other half of the atomic write: a
    power cut mid-rename is the normal way a Pico's filesystem loses a file,
    and one of the three is always intact.
    """
    for candidate in (path, path + ".bak", path + ".tmp"):
        try:
            with open(candidate, "r") as fh:
                payload = ujson.loads(fh.read())
                if isinstance(payload, dict):
                    return payload
        except Exception:
            pass
    return {}


def save_json_store(path, payload, label=""):
    """Write via a temp file and a rename, keeping the previous copy as `.bak`.

    Never raises: a store is a cache, and failing a page load because flash is
    full would turn a degraded device into a dead one.
    """
    tmp_file = path + ".tmp"
    bak_file = path + ".bak"

    try:
        with open(tmp_file, "w") as fh:
            fh.write(ujson.dumps(payload))

        try:
            os.remove(bak_file)
        except Exception:
            pass

        try:
            os.rename(path, bak_file)
        except Exception:
            pass

        os.rename(tmp_file, path)
    except Exception as error:
        log("%s store save failed: %s" % (label or path, error))


def parse_provider_history(points, datetime_key, intensity_getter):
    history = []
    for point in points:
        point_time = point.get(datetime_key)
        value = safe_float(intensity_getter(point))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


def _upsert_sample(samples, sample, retention_hours):
    """This hour's reading written into the store, aged out and sorted.

    An upsert rather than an append: the hour is the key, so a second poll
    inside the same hour replaces the first instead of leaving two points on
    the same bucket.
    """
    hour = sample["ts"]
    for idx, item in enumerate(samples):
        if int(item.get("ts") or 0) == hour:
            samples[idx] = sample
            break
    else:
        samples.append(sample)

    cutoff = hour - (retention_hours * 3600)
    kept = [item for item in samples if int(item.get("ts") or 0) >= cutoff]
    kept.sort(key=lambda item: int(item.get("ts") or 0))
    return kept


def _window_history(samples, start, end):
    """The stored samples covering [start, end], hour by hour.

    Returns (history, city, country_code); the city is the first one named in
    the window and the country the last, which is how they were picked when
    this was part of `fetch_history`.
    """
    by_hour = {}
    for item in samples:
        ts = int(item.get("ts") or 0)
        if ts > 0:
            by_hour[ts] = item

    history = []
    city = None
    resolved_cc = None
    hour = floor_hour_epoch(start)
    end_hour = floor_hour_epoch(end)
    while hour <= end_hour:
        sample = by_hour.get(hour)
        value = safe_float(sample.get("carbonIntensity")) if sample else None
        if value is not None:
            history.append({"datetime": epoch_to_iso_z(hour), "carbonIntensity": value})
            city = city or sample.get("city")
            resolved_cc = sample.get("cc") or resolved_cc
        hour += 3600
    return history, city, resolved_cc


def _latest_history(samples, end):
    """One point from the newest sample, or None when it has no usable value.

    The fallback for a window the store cannot cover yet — the first day of
    uptime, while the curve is still filling in.
    """
    latest = samples[-1]
    latest_ci = safe_float(latest.get("carbonIntensity"))
    if latest_ci is None:
        return None
    latest_ts = int(latest.get("ts") or floor_hour_epoch(end))
    return (
        [{"datetime": epoch_to_iso_z(latest_ts), "carbonIntensity": latest_ci}],
        latest.get("city"),
        latest.get("cc"),
    )


class EmissionsProvider(ABC):
    provider_name: str

    @abstractmethod
    def is_enabled(self, country_code: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_history(
        self,
        latitude: float,
        longitude: float,
        country_code: str,
        start: datetime,
        end: datetime,
    ) -> dict:
        raise NotImplementedError


class SampledProvider(EmissionsProvider):
    """Base for providers that publish only a current value, no history.

    The device ranks the coming hours against the recent ones, so it needs a
    curve; these APIs answer "what is it now" and nothing else. Each poll is
    appended to a small on-flash store and the history is served from there,
    filling in over the first day of uptime.

    Subclasses set `store_file` and implement `fetch_current`.
    """

    store_file = ""
    collect_interval_sec = 5 * 60
    retention_hours = 24 * 14

    # Class-level on purpose: fw_providers builds a fresh instance per request,
    # so an instance attribute would reset the cooldown every time and poll the
    # upstream API on every single page load.
    _next_collect_after = 0

    @abstractmethod
    def fetch_current(self, latitude, longitude, country_code):
        """Return (intensity, city, country_code) for right now.

        Raise ProviderError when the upstream value is missing or unusable.
        """
        raise NotImplementedError

    def sample_hour(self, now_epoch):
        """Hour bucket a fresh sample belongs to. Overridable by providers that
        know the hour their reading actually covers."""
        return floor_hour_epoch(now_epoch)

    def _defer(self, seconds):
        type(self)._next_collect_after = int(time.time()) + seconds

    def _load_store(self):
        samples = load_json_store(self.store_file).get("samples")
        return samples if isinstance(samples, list) else []

    def _save_store(self, samples):
        save_json_store(self.store_file, {"samples": samples}, self.provider_name)

    def _collect_if_due(self, latitude, longitude, country_code):
        now = int(time.time())
        samples = self._load_store()

        if now < self._next_collect_after:
            return samples

        try:
            intensity, city, resolved_cc = self.fetch_current(
                latitude, longitude, country_code
            )
            sample = {
                "ts": self.sample_hour(now),
                "carbonIntensity": intensity,
                "city": city or "",
                "cc": (resolved_cc or country_code or "").upper(),
            }
            samples = _upsert_sample(samples, sample, self.retention_hours)
            self._save_store(samples)
            self._defer(self.collect_interval_sec)
            return samples
        except Exception as error:
            log("%s collect failed: %s" % (self.provider_name, error))
            self._defer(60)
            return samples

    def fetch_history(self, latitude, longitude, country_code, start, end):
        cc = (country_code or "").upper()
        samples = self._collect_if_due(latitude, longitude, cc)

        if not samples:
            raise ProviderError("%s store is empty" % self.provider_name)

        history, city, resolved_cc = _window_history(samples, start, end)
        if not history:
            fallback = _latest_history(samples, end)
            if fallback is None:
                raise ProviderError("%s history unavailable" % self.provider_name)
            history, city, resolved_cc = fallback

        return {
            "city": city or resolved_cc or cc or self.provider_name,
            "history": history,
            "_provider": self.provider_name,
        }
