import os
import time
import ujson
from abc import ABC, abstractmethod
from datetime import datetime
from utils import ProviderError, floor_hour_epoch, epoch_to_iso_z, log, safe_float


def parse_provider_history(points, datetime_key, intensity_getter):
    history = []
    for point in points:
        point_time = point.get(datetime_key)
        value = safe_float(intensity_getter(point))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


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
        for candidate in (
            self.store_file,
            self.store_file + ".bak",
            self.store_file + ".tmp",
        ):
            try:
                with open(candidate, "r") as fh:
                    payload = ujson.loads(fh.read()) or {}
                    samples = payload.get("samples") or []
                    if isinstance(samples, list):
                        return samples
            except Exception:
                pass
        return []

    def _save_store(self, samples):
        payload = {"samples": samples}
        tmp_file = self.store_file + ".tmp"
        bak_file = self.store_file + ".bak"

        try:
            with open(tmp_file, "w") as fh:
                fh.write(ujson.dumps(payload))

            try:
                os.remove(bak_file)
            except Exception:
                pass

            try:
                os.rename(self.store_file, bak_file)
            except Exception:
                pass

            os.rename(tmp_file, self.store_file)
        except Exception as error:
            log("%s store save failed: %s" % (self.provider_name, error))

    def _collect_if_due(self, latitude, longitude, country_code):
        now = int(time.time())
        samples = self._load_store()

        if now < self._next_collect_after:
            return samples

        try:
            intensity, city, resolved_cc = self.fetch_current(
                latitude, longitude, country_code
            )
            hour = self.sample_hour(now)
            sample = {
                "ts": hour,
                "carbonIntensity": intensity,
                "city": city or "",
                "cc": (resolved_cc or country_code or "").upper(),
            }

            # Upsert current hour sample.
            replaced = False
            for idx, item in enumerate(samples):
                if int(item.get("ts") or 0) == hour:
                    samples[idx] = sample
                    replaced = True
                    break
            if not replaced:
                samples.append(sample)

            cutoff = hour - (self.retention_hours * 3600)
            samples = [item for item in samples if int(item.get("ts") or 0) >= cutoff]
            samples.sort(key=lambda x: int(x.get("ts") or 0))
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

        by_hour = {}
        city = None
        resolved_cc = cc
        for item in samples:
            ts = int(item.get("ts") or 0)
            if ts <= 0:
                continue
            by_hour[ts] = item

        history = []
        hour = floor_hour_epoch(start)
        end_hour = floor_hour_epoch(end)
        while hour <= end_hour:
            sample = by_hour.get(hour)
            if sample:
                value = safe_float(sample.get("carbonIntensity"))
                if value is not None:
                    history.append(
                        {"datetime": epoch_to_iso_z(hour), "carbonIntensity": value}
                    )
                    city = city or sample.get("city")
                    resolved_cc = sample.get("cc") or resolved_cc
            hour += 3600

        if not history:
            # Fallback to latest known value if requested range has no samples yet.
            latest = samples[-1]
            latest_ts = int(latest.get("ts") or floor_hour_epoch(end))
            latest_ci = safe_float(latest.get("carbonIntensity"))
            if latest_ci is None:
                raise ProviderError("%s history unavailable" % self.provider_name)
            history = [
                {"datetime": epoch_to_iso_z(latest_ts), "carbonIntensity": latest_ci}
            ]
            city = latest.get("city")
            resolved_cc = latest.get("cc") or resolved_cc

        return {
            "city": city or resolved_cc or self.provider_name,
            "history": history,
            "_provider": self.provider_name,
        }
