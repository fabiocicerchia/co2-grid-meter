#!/usr/bin/env python3
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

from pico.export import summary_from_window, window_csv
from pico.providers.simulated import SimulatedProvider
from pico.recommendation import compute_recommendation
from pico.utils import floor_hour, iso_utc

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    country: str
    city: str
    source: str


def resolve_from_ip():
    try:
        # ip-api.com's free tier 403s on https:// (HTTPS is a paid-plan feature) —
        # plain http is deliberate here, not an oversight. Low-sensitivity lookup
        # (approximate geo-IP for display defaults), no credentials involved.
        response = requests.get(
            "http://ip-api.com/json/", timeout=4
        )  # nosemgrep: request-with-http
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


class MockPicoHandler(BaseHTTPRequestHandler):
    """The firmware's endpoint shapes, backed by the simulated provider.

    The provider is a class attribute rather than an `__init__` argument:
    `HTTPServer` constructs a handler per request and controls that signature,
    so `create_handler` binds one onto a subclass instead.
    """

    config = None
    logger = None
    provider = None

    def _window_response(self, location, start_time, end_time):
        window_payload = self.provider.fetch_history(
            location.latitude,
            location.longitude,
            location.country,
            start_time,
            end_time,
        )
        return {
            "city": location.city,
            "country": location.country,
            "lat": location.latitude,
            "lon": location.longitude,
            "history": window_payload["history"],
            "_provider": window_payload["provider"],
            "_geo_source": location.source,
        }

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        location = resolve_from_ip()

        status_code = 404
        payload = {}
        text_body = None
        content_type = "application/json"

        try:
            if url.path == "/status":
                now_utc = floor_hour(datetime.now(timezone.utc))
                start_time = now_utc - timedelta(hours=36) - timedelta(days=7)
                end_time = now_utc + timedelta(hours=12) - timedelta(days=7)
                payload = self._window_response(location, start_time, end_time)
                current_carbon_intensity = float(
                    payload["history"][-1]["carbonIntensity"]
                )
                payload["datetime"] = iso_utc(now_utc)
                payload["carbonIntensity"] = current_carbon_intensity
                payload["recommendation"] = compute_recommendation(
                    current_carbon_intensity,
                    payload["history"],
                    int(now_utc.timestamp()),
                )
                status_code = 200
            elif url.path == "/em/window":
                back_hours = int(query.get("back_hours", [48])[0])
                end_time = floor_hour(datetime.now(timezone.utc))
                start_time = end_time - timedelta(hours=back_hours)
                payload = self._window_response(location, start_time, end_time)
                status_code = 200
            elif url.path == "/em/window-overlay":
                now_time = floor_hour(datetime.now(timezone.utc))
                start_time = now_time - timedelta(hours=48, days=7)
                end_time = now_time + timedelta(hours=12) - timedelta(days=7)
                payload = self._window_response(location, start_time, end_time)
                status_code = 200
            elif url.path == "/em/window.csv":
                back_hours = int(query.get("back_hours", [48])[0])
                end_time = floor_hour(datetime.now(timezone.utc))
                start_time = end_time - timedelta(hours=back_hours)
                window = self._window_response(location, start_time, end_time)
                text_body = window_csv(window)
                content_type = "text/csv"
                status_code = 200
            elif url.path == "/em/summary":
                now_utc = floor_hour(datetime.now(timezone.utc))
                window = self._window_response(
                    location, now_utc - timedelta(hours=48), now_utc
                )
                current = float(window["history"][-1]["carbonIntensity"])
                payload = summary_from_window(
                    window,
                    current,
                    compute_recommendation(
                        current, window["history"], int(now_utc.timestamp())
                    ),
                    iso_utc(now_utc),
                    city=location.city,
                    cc=location.country,
                    provider="simulated",
                )
                status_code = 200
        except Exception as error:
            status_code = 502
            payload = {"error": str(error)}
            text_body = None
            content_type = "application/json"
            self.logger.exception("Failed %s", url.path)

        # text_body is the CSV export's escape hatch: everything else answers
        # with JSON, and a CSV serialised as JSON would be a string, not a file.
        body = text_body if text_body is not None else json.dumps(payload)
        self.protocol_version = "HTTP/1.1"
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf8"))


def create_handler(*, config, logger) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class bound to the given dependencies."""
    return type(
        "Handler",
        (MockPicoHandler,),
        {"config": config, "logger": logger, "provider": SimulatedProvider()},
    )
