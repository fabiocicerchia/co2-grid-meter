"""CO2Signal provider for firmware."""

from utils import ProviderError, http_get_json, safe_float, urlencode_simple

from config import CONFIG
from providers.base import SampledProvider

# The keys CO2Signal has answered under, newest naming first. The payload shape
# has changed more than once and old deployments still see the old names.
INTENSITY_KEYS = ("carbonIntensity", "carbon_intensity", "intensity", "value")
CITY_KEYS = ("countryName", "zone", "country")
COUNTRY_CODE_KEYS = ("countryCode", "country_code")


def _first_truthy(data, keys):
    """The first truthy value among `keys`.

    Exactly what the `or` chain this replaced returned, including its tail: when
    none of the keys holds a truthy value, the last one's value is the answer,
    so a genuine zero under the final key still reads as zero.
    """
    value = None
    for key in keys:
        value = data.get(key)
        if value:
            break
    return value


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

        cc = _first_truthy(data, COUNTRY_CODE_KEYS)
        if isinstance(cc, str):
            cc = cc.upper()
        return (
            safe_float(_first_truthy(data, INTENSITY_KEYS)),
            _first_truthy(data, CITY_KEYS),
            cc,
        )

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
