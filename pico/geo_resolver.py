"""Resolves request geo information from query overrides or client IP."""

import logging
import time
from requests import Session
from urllib.parse import urlparse, parse_qs
from .config import AppConfig
from pico.models import GeoLocation

LOGGER = logging.getLogger(__name__)


class GeoResolver:
    """Resolves user location in a deterministic way."""

    def __init__(self, config: AppConfig, session: Session):
        self._config = config
        self._session = session

    def resolve(self, http_request) -> GeoLocation:
        override = self._resolve_from_query_string(http_request)
        if override is not None:
            return override

        client_ip_address = self._get_client_ip_address(http_request)
        if not client_ip_address or client_ip_address in ("127.0.0.1", "::1"):
            return self._default_location("default")

        ip_location = self._resolve_from_ip(client_ip_address)
        if ip_location is not None:
            return ip_location

        return self._default_location("default")

    def _resolve_from_query_string(self, http_request):
        query = parse_qs(urlparse(http_request.path).query)

        query_latitude = query.get("lat", [None])[0]
        query_longitude = query.get("lon", [None])[0]
        if query_latitude is None or query_longitude is None:
            return None

        try:
            return GeoLocation(
                latitude=float(query_latitude),
                longitude=float(query_longitude),
                country=(query.get("country", ["—"])[0] or "—").upper(),
                city=query.get("city", ["—"])[0] or "—",
                source="override",
            )
        except ValueError:
            return None

    def _resolve_from_ip(self, client_ip_address: str):
        try:
            response = self._session.get(
                f"http://ip-api.com/json/{client_ip_address}", timeout=4
            )
            payload = response.json()
            if payload.get("status") != "success":
                return None
            return GeoLocation(
                latitude=float(payload["lat"]),
                longitude=float(payload["lon"]),
                country=(payload.get("countryCode") or "").upper(),
                city=payload.get("city") or "—",
                source="ip",
            )
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Unable to resolve geo from IP: %s", error)
            return None

    def _get_client_ip_address(self, http_request) -> str:
        return (http_request.client_address[0] or "").strip()

    def _default_location(self, source_label: str) -> GeoLocation:
        return GeoLocation(
            latitude=self._config.defaults.latitude,
            longitude=self._config.defaults.longitude,
            country=self._config.defaults.country,
            city=self._config.defaults.city,
            source=source_label,
        )
