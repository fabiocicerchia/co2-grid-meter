#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from requests import Session

from pico import GeoResolver, WindowService, build_status, providers
from pico.ttl_cache import TtlCache
from pico.utils import floor_hour


def _make_window_service(config, http_session: Session) -> WindowService:
    return WindowService(
        config,
        [
            providers.UKCarbonIntensityProvider(http_session),
            providers.EntsoeProvider(http_session, config),
            providers.WattTimeProvider(http_session, config),
            providers.ElectricityMapsProvider(http_session, config),
            providers.SimulatedProvider(config),
        ],
    )


def create_handler(*, config: Any, logger: Any, http_session: Session) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class bound to the given dependencies."""

    geo_resolver = GeoResolver(config, http_session)
    window_service = _make_window_service(config, http_session)
    response_cache = TtlCache(getattr(config, "cache_refresh_seconds", 3600))

    class Handler(BaseHTTPRequestHandler):
        def _cached(self, key, factory):
            return response_cache.get_or_set(key, factory)

        def _window_response(self, location, start_time, end_time):
            window_payload = window_service.fetch_window(location, start_time, end_time)
            return {
                "city": location.city,
                "country": location.country,
                "lat": location.latitude,
                "lon": location.longitude,
                "history": window_payload["history"],
                "_provider": window_payload["provider"],
                "_geo_source": location.source,
            }

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            query = parse_qs(url.query)
            location = geo_resolver.resolve(self)

            status_code = 404
            payload = {}

            try:
                if url.path == "/status":
                    cache_key = ("status", location)
                    payload = self._cached(
                        cache_key,
                        lambda: build_status(window_service, location),
                    )
                    status_code = 200
                elif url.path == "/em/window":
                    back_hours = int(query.get("back_hours", [48])[0])
                    end_time = floor_hour(datetime.now(timezone.utc))
                    start_time = end_time - timedelta(hours=back_hours)
                    cache_key = (
                        "window",
                        location,
                        back_hours,
                        start_time.isoformat(),
                        end_time.isoformat(),
                    )
                    payload = self._cached(
                        cache_key,
                        lambda: self._window_response(location, start_time, end_time),
                    )
                    status_code = 200
                elif url.path == "/em/window-overlay":
                    now_time = floor_hour(datetime.now(timezone.utc))
                    start_time = now_time - timedelta(hours=48, days=7)
                    end_time = now_time + timedelta(hours=12) - timedelta(days=7)
                    cache_key = (
                        "overlay",
                        location,
                        start_time.isoformat(),
                        end_time.isoformat(),
                    )
                    payload = self._cached(
                        cache_key,
                        lambda: self._window_response(location, start_time, end_time),
                    )
                    status_code = 200
            except Exception as error:  # noqa: BLE001
                status_code = 502
                payload = {"error": str(error)}
                logger.exception("Failed %s", url.path)

            body = json.dumps(payload)
            self.protocol_version = "HTTP/1.1"
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode("utf8"))

    return Handler
