"""Builds status response from window data and recommendation logic."""

from datetime import datetime, timedelta, timezone

from pico.models import GeoLocation
from pico.recommendation import compute_recommendation
from pico.utils import floor_hour, iso_utc
from pico.window_service import WindowService


def build_status(window_service: WindowService, location: GeoLocation):
    now_utc = floor_hour(datetime.now(timezone.utc))

    current_window = window_service.fetch_window(
        location=location,
        start=now_utc - timedelta(hours=48),
        end=now_utc,
    )
    if not current_window.get("history"):
        raise RuntimeError("No history returned")

    current_carbon_intensity = float(
        current_window["history"][-1]["carbonIntensity"])

    overlay_window = window_service.fetch_window(
        location=location,
        start=now_utc - timedelta(hours=36) - timedelta(days=7),
        end=now_utc + timedelta(hours=12) - timedelta(days=7),
    )

    return {
        "datetime": iso_utc(now_utc),
        "lat": location.latitude,
        "lon": location.longitude,
        "city": location.city,
        "country": location.country,
        "carbonIntensity": current_carbon_intensity,
        "recommendation": compute_recommendation(
            current_carbon_intensity,
            overlay_window.get("history") or [],
            now_utc,
        ),
        "_provider": current_window["provider"],
        "_geo_source": location.source,
    }
