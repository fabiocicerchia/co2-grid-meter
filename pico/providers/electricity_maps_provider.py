"""Electricity Maps provider adapter."""

from requests import Session

from ..config import AppConfig
from pico.providers.base import EmissionsProvider
from pico.utils import iso_utc


class ElectricityMapsProvider(EmissionsProvider):
    """Fetches historical intensity from Electricity Maps API."""

    provider_name = "electricitymaps"

    def __init__(self, session: Session, config: AppConfig):
        self._session = session
        self._config = config

    def is_enabled(self, country_code: str) -> bool:
        del country_code
        return bool(
            self._config.providers.electricity_maps.enabled
            and self._config.providers.electricity_maps.token
        )

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del country_code
        response = self._session.get(
            f"{self._config.providers.electricity_maps.base_url}/v3/carbon-intensity/past-range",
            headers={"auth-token": self._config.providers.electricity_maps.token},
            params={
                "lat": latitude,
                "lon": longitude,
                "start": iso_utc(start),
                "end": iso_utc(end),
                "temporalGranularity": "hourly",
            },
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        history = payload.get("history") or payload.get("data") or []
        return {
            "history": [
                {
                    "datetime": point["datetime"],
                    "carbonIntensity": point["carbonIntensity"],
                }
                for point in history
            ],
            "provider": self.provider_name,
        }
