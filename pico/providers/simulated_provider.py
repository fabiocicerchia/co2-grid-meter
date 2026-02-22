"""Simulated provider used as local fallback."""

import math
import random
from datetime import timedelta

from pico.providers.base import EmissionsProvider
from pico.utils import iso_utc


class SimulatedProvider(EmissionsProvider):
    """Generates synthetic but plausible hourly emissions data."""

    provider_name = "sim_fallback"

    def is_enabled(self, country_code: str) -> bool:
        return True

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del latitude, longitude, country_code
        history = []
        cursor = start
        while cursor <= end:
            day_seconds = 24 * 3600
            phase = (cursor.timestamp() % day_seconds) / day_seconds
            simulated_value = (
                260
                + 90 * math.sin(2 * math.pi * (phase - 0.2))
                + 12 * (random.random() - 0.5)
            )
            history.append(
                {
                    "datetime": iso_utc(cursor),
                    "carbonIntensity": int(round(max(80.0, simulated_value))),
                }
            )
            cursor += timedelta(hours=1)
        return {"history": history, "provider": self.provider_name}
