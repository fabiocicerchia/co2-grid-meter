"""Carbon Intensity API provider (https://ci-api.fabiocicerchia.it).

Keyless, 213 countries, plus ENTSO-E/EIA/NEM bidding zones where the operator
publishes below national level. It serves the last hour only, so this is a
`SampledProvider`: the curve is built locally, one poll at a time.
"""

import time

from ci_api_parse import freshness_error, pick_intensity, reading_path
from utils import ProviderError, floor_hour_epoch, http_get_json, iso_z_to_epoch, log

from config import CONFIG
from providers.base import SampledProvider


class CiApiProvider(SampledProvider):
    provider_name = "ci_api"
    store_file = "ci_api_store.json"

    # The API is rate-limited to 1 request per 10s per IP (a CDN rule, so a 429
    # is all you get). Five minutes is the same cadence as the other sampled
    # providers and leaves the limit two orders of magnitude of headroom.
    collect_interval_sec = 5 * 60

    _next_collect_after = 0
    _hour_start_epoch = None

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.ci_api.enabled

    def sample_hour(self, now_epoch):
        # The reading names the hour it covers; bucketing it by wall-clock
        # instead would file a 14:00 reading under 15:00 whenever the hourly
        # pipeline runs late.
        if self._hour_start_epoch is not None:
            return floor_hour_epoch(self._hour_start_epoch)
        return floor_hour_epoch(now_epoch)

    def fetch_current(self, latitude, longitude, country_code):
        del latitude, longitude

        if not CONFIG.providers.ci_api.enabled:
            raise ProviderError("Carbon Intensity API disabled")

        code = (CONFIG.providers.ci_api.country_override or country_code or "").upper()
        zone = CONFIG.providers.ci_api.zone
        try:
            path = reading_path(code, zone)
        except ValueError as error:
            raise ProviderError("Carbon Intensity API: %s" % error)

        url = CONFIG.providers.ci_api.base_url.rstrip("/") + path
        payload = http_get_json(url, "Carbon Intensity API")

        problem = freshness_error(
            payload,
            iso_z_to_epoch(payload.get("generated_at")),
            int(time.time()),
        )
        if problem:
            raise ProviderError("Carbon Intensity API: %s" % problem)

        intensity, figure = pick_intensity(payload)
        if intensity is None:
            raise ProviderError("Carbon Intensity API: no intensity figure in payload")
        if figure != "consumption_lifecycle":
            # Expected on zone endpoints, which carry no consumption figures.
            log("Carbon Intensity API: fell back to %s for %s" % (figure, path))

        self._hour_start_epoch = iso_z_to_epoch(payload.get("hour_start"))
        city = payload.get("zone") or payload.get("country") or code
        return intensity, city, payload.get("country_code") or code
