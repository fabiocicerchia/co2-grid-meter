"""CO2Signal provider for firmware."""

import ujson
import os
import time

from utils import ProviderError, http_get_json, epoch_to_iso_z
from providers.base import parse_provider_history
from config import CONFIG
from utils import floor_hour_epoch, urlencode_simple, safe_float, log

from providers.base import EmissionsProvider


class Co2SignalProvider(EmissionsProvider):
    provider_name = "co2signal"

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.co2signal.enabled

    def parse_payload(self, payload):
        return parse_provider_history(
            payload.get("history") or payload.get("data") or [],
            datetime_key="datetime",
            intensity_getter=lambda point: point.get("carbonIntensity"),
        )

    def fetch_history(self, latitude, longitude, country_code, start, end):
        if not (
            CONFIG.providers.electricity_maps.enabled
            and CONFIG.providers.electricity_maps.token
        ):
            raise ProviderError("Electricity Maps disabled/missing token")

        query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
            str(latitude),
            str(longitude),
            epoch_to_iso_z(start),
            epoch_to_iso_z(end),
        )
        api_url = (
            CONFIG.providers.electricity_maps.base_url
            + "/v3/carbon-intensity/past-range?"
            + query
        )

        payload = http_get_json(
            api_url,
            "EM",
            headers={"auth-token": CONFIG.providers.electricity_maps.token},
            content_parser=True,
        )

        return {
            "city": payload.get("zone") or payload.get("city") or "ElectricityMaps",
            "history": self.parse_payload(payload),
            "_provider": "em",
        }

    _next_collect_after = 0
    _store_file = "co2signal_store.json"
    _collect_interval_sec = 5 * 60
    _retention_hours = 24 * 14

    def _load_store(self):
        for candidate in (
            self._store_file,
            self._store_file + ".bak",
            self._store_file + ".tmp",
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
        tmp_file = self._store_file + ".tmp"
        bak_file = self._store_file + ".bak"

        try:
            with open(tmp_file, "w") as fh:
                fh.write(ujson.dumps(payload))

            try:
                os.remove(bak_file)
            except Exception:
                pass

            try:
                os.rename(self._store_file, bak_file)
            except Exception:
                pass

            os.rename(tmp_file, self._store_file)
        except Exception as error:
            log("CO2Signal store save failed: %s" % error)

    def _extract_intensity(self, payload):
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            data = payload if isinstance(payload, dict) else {}

        intensity = safe_float(
            data.get("carbonIntensity")
            or data.get("carbon_intensity")
            or data.get("intensity")
            or data.get("value")
        )
        city = data.get("countryName") or data.get("zone") or data.get("country")
        cc = data.get("countryCode") or data.get("country_code")
        if isinstance(cc, str):
            cc = cc.upper()
        return intensity, city, cc

    def _fetch_current(lat, lon, country_code):
        if not (
            CONFIG.providers.co2signal.enabled and CONFIG.providers.co2signal.token
        ):
            raise ProviderError("CO2Signal disabled/missing token")

        params = {"lat": str(lat), "lon": str(lon)}
        if country_code:
            params["countryCode"] = country_code

        url = CONFIG.providers.co2signal.base_url + "?" + urlencode_simple(params)
        payload = http_get_json(
            url,
            "CO2Signal",
            headers={"auth-token": CONFIG.providers.co2signal.token},
            content_parser=True,
        )
        intensity, city, cc = self._extract_intensity(payload)
        if intensity is None:
            raise ProviderError("CO2Signal missing carbonIntensity")
        return intensity, city, cc

    def _collect_if_due(self, lat, lon, country_code):
        now = int(time.time())
        samples = self._load_store()

        if now < self._next_collect_after:
            return samples

        try:
            intensity, city, resolved_cc = self._fetch_current(lat, lon, country_code)
            hour = floor_hour_epoch(now)
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

            cutoff = hour - (self._retention_hours * 3600)
            samples = [item for item in samples if int(item.get("ts") or 0) >= cutoff]
            samples.sort(key=lambda x: int(x.get("ts") or 0))
            self._save_store(samples)
            self._next_collect_after = now + self._collect_interval_sec
            return samples
        except Exception as error:
            log("CO2Signal collect failed: %s" % error)
            self._next_collect_after = now + 60
            return samples

    def fetch_history(self, latitude, longitude, country_code, start, end):
        cc = (country_code or "").upper()
        samples = self._collect_if_due(latitude, longitude, cc)

        if not samples:
            raise ProviderError("CO2Signal store is empty")

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
                raise ProviderError("CO2Signal history unavailable")
            history = [
                {"datetime": epoch_to_iso_z(latest_ts), "carbonIntensity": latest_ci}
            ]
            city = latest.get("city")
            resolved_cc = latest.get("cc") or resolved_cc

        return {
            "city": city or resolved_cc or "CO2Signal",
            "history": history,
            "_provider": "co2signal",
        }
