"""Electricity Maps provider for firmware."""

from utils import ProviderError, epoch_to_iso_z, http_get_json

from config import CONFIG
from providers.base import EmissionsProvider, parse_provider_history


class ElectricityMapsProvider(EmissionsProvider):
    provider_name = "electricity-maps"

    def missing(self, country_code: str) -> list:
        return [] if CONFIG.providers.electricity_maps.token else ["providers.electricity_maps.token"]

    def is_enabled(self, country_code: str) -> bool:
        return bool(CONFIG.providers.electricity_maps.enabled) and not self.missing(country_code)

    def parse_payload(self, payload):
        return parse_provider_history(
            payload.get("history") or payload.get("data") or [],
            datetime_key="datetime",
            intensity_getter=lambda point: point.get("carbonIntensity"),
        )

    def fetch_history(self, latitude, longitude, country_code, start, end):
        missing = self.missing(country_code)
        if missing:
            raise ProviderError("Electricity Maps needs %s" % ", ".join(missing))

        query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
            str(latitude),
            str(longitude),
            epoch_to_iso_z(start),
            epoch_to_iso_z(end),
        )
        api_url = CONFIG.providers.electricity_maps.base_url + "/v3/carbon-intensity/past-range?" + query

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
