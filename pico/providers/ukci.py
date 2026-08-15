"""UK Carbon Intensity provider for firmware."""

import time

from utils import _format_timestamp, http_get_json

from config import CONFIG
from providers.base import EmissionsProvider, parse_provider_history


class UkciProvider(EmissionsProvider):
    provider_name = "ukci"

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.ukci_enabled  # TODO: change to ukci.enabled

    def format_timestamp(self, epoch_value):
        return _format_timestamp(time.gmtime(epoch_value), include_seconds=False) + "Z"

    def parse_payload(self, payload):
        return parse_provider_history(
            payload.get("data") or [],
            datetime_key="from",
            intensity_getter=lambda point: (
                (point.get("intensity") or {}).get("actual")
                or (point.get("intensity") or {}).get("forecast")
            ),
        )

    def fetch_history(self, latitude, longitude, country_code, start, end):
        api_url = "https://api.carbonintensity.org.uk/intensity/%s/%s" % (
            self.format_timestamp(start),
            self.format_timestamp(end),
        )
        payload = http_get_json(api_url, "UKCI")
        return {
            "city": "Great Britain",
            "history": self.parse_payload(payload),
            "_provider": "uk",
        }
