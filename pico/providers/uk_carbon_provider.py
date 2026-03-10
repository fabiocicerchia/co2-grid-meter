"""UK Carbon Intensity provider adapter."""

from requests import Session

from providers.base import EmissionsProvider
from config import CONFIG


class UKCarbonIntensityProvider(EmissionsProvider):
    """Fetches hourly intensity for UK regions."""

    provider_name = "ukcarbonintensity"

    def __init__(self, session: Session):
        self._session = session

    def is_enabled(self, country_code: str) -> bool:
        return country_code in ("GB", "UK")

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del latitude, longitude, country_code
        url = (
            "https://api.carbonintensity.org.uk/intensity/"
            f"{start.strftime('%Y-%m-%dT%H:%MZ')}/{end.strftime('%Y-%m-%dT%H:%MZ')}"
        )
        response = self._session.get(url, timeout=20)
        response.raise_for_status()

        history = []
        for point in response.json().get("data") or []:
            intensity_payload = point.get("intensity") or {}
            carbon_intensity = intensity_payload.get("actual") or intensity_payload.get(
                "forecast"
            )
            timestamp = point.get("from")
            if carbon_intensity is None or not timestamp:
                continue
            history.append(
                {"datetime": timestamp, "carbonIntensity": int(carbon_intensity)}
            )

        return {"history": history, "provider": self.provider_name}
