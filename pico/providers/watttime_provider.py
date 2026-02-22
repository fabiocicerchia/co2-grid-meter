"""WattTime provider adapter."""

import time
from datetime import datetime

from requests import Session
from requests.auth import HTTPBasicAuth

from providers.base import EmissionsProvider
from providers.constants import WT_REGION_MAP
from utils import floor_hour, iso_utc
from config import CONFIG

LBS_PER_MWH_TO_GRAMS_PER_KWH = 0.45359237
TOKEN_CACHE_TTL_SEC = 1500


class WattTimeProvider(EmissionsProvider):
    """Fetches historical emissions from WattTime."""

    provider_name = "watttime"

    def __init__(self, session: Session):
        self._session = session
        self._config = CONFIG
        self._cached_token = ""
        self._token_created_at = 0.0

    def is_enabled(self, country_code: str) -> bool:
        del country_code
        return bool(
            self._config.providers.watttime.enabled
            and self._config.providers.watttime.username
            and self._config.providers.watttime.password
        )

    def _get_token(self) -> str:
        if (
            self._cached_token
            and (time.time() - self._token_created_at) < TOKEN_CACHE_TTL_SEC
        ):
            return self._cached_token

        response = self._session.get(
            f"{self._config.providers.watttime.base_url}/login",
            auth=HTTPBasicAuth(
                self._config.providers.watttime.username,
                self._config.providers.watttime.password,
            ),
            timeout=10,
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise RuntimeError("WattTime login returned no token")

        self._cached_token = token
        self._token_created_at = time.time()
        return token

    def _pick_region(self, country_code: str) -> str:
        if self._config.providers.watttime.region_override:
            return self._config.providers.watttime.region_override
        if self._config.providers.watttime.region_by_country:
            return WT_REGION_MAP.get(country_code, "")
        return ""

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del latitude, longitude
        region_code = self._pick_region(country_code)
        if not region_code:
            raise RuntimeError("WattTime region unavailable")

        token = self._get_token()
        response = self._session.get(
            f"{self._config.providers.watttime.base_url}/v3/historical",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "region": region_code,
                "signal_type": self._config.providers.watttime.signal,
                "start": iso_utc(start),
                "end": iso_utc(end),
            },
            timeout=25,
        )
        if response.status_code == 403:
            raise PermissionError("WattTime region not available for account")
        response.raise_for_status()

        hourly_buckets = {}
        for point in response.json().get("data") or []:
            point_time = point.get("point_time")
            value = point.get("value")
            if point_time is None or value is None:
                continue

            # WattTime returns frequent points; aggregate to full hours.
            bucket_timestamp = floor_hour(
                datetime.fromisoformat(point_time.replace("Z", "+00:00"))
            )
            bucket = hourly_buckets.setdefault(
                bucket_timestamp, {"sum": 0.0, "count": 0}
            )
            bucket["sum"] += float(value)
            bucket["count"] += 1

        history = []
        for timestamp in sorted(hourly_buckets):
            average_lbs_per_mwh = (
                hourly_buckets[timestamp]["sum"] / hourly_buckets[timestamp]["count"]
            )
            history.append(
                {
                    "datetime": iso_utc(timestamp),
                    "carbonIntensity": int(
                        round(average_lbs_per_mwh * LBS_PER_MWH_TO_GRAMS_PER_KWH)
                    ),
                }
            )

        return {
            "history": history,
            "provider": f"{self.provider_name}:{region_code}:{self._config.providers.watttime.signal}",
        }
