"""CO2Signal provider for firmware."""

from utils import ProviderError, http_get_json, safe_float, urlencode_simple

from config import CONFIG
from providers.base import SampledProvider


class Co2SignalProvider(SampledProvider):
    provider_name = "co2signal"
    store_file = "co2signal_store.json"

    _next_collect_after = 0

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.co2signal.enabled

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

    def fetch_current(self, latitude, longitude, country_code):
        if not (
            CONFIG.providers.co2signal.enabled and CONFIG.providers.co2signal.token
        ):
            raise ProviderError("CO2Signal disabled/missing token")

        params = {"lat": str(latitude), "lon": str(longitude)}
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
