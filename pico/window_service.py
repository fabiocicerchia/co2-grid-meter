"""Window retrieval orchestration with provider failover and caching."""

import logging
import time
from datetime import datetime

from pico.config import AppConfig
from pico.models import GeoLocation
from pico.providers.base import EmissionsProvider
from pico.resilience import CircuitBreaker, retry_with_backoff

LOGGER = logging.getLogger(__name__)


class WindowService:
    """Fetches emissions windows from available providers with resilience."""

    def __init__(self, config: AppConfig, providers: list[EmissionsProvider]):
        self._config = config
        self._providers = providers
        self._ = {}
        self._breakers = {
            provider.provider_name: CircuitBreaker() for provider in self._providers
        }

    def fetch_window(self, location: GeoLocation, start: datetime, end: datetime):
        payload = self._fetch_from_first_available_provider(
            location, start, end)
        return payload

    def _fetch_from_first_available_provider(
        self, location: GeoLocation, start: datetime, end: datetime
    ):
        provider_errors = []
        for provider in self._providers:
            if not provider.is_enabled(location.country):
                continue

            provider_circuit_breaker = self._breakers[provider.provider_name]
            if not provider_circuit_breaker.allow_request():
                LOGGER.warning(
                    "Skipping provider due to open circuit: %s", provider.provider_name
                )
                continue

            try:
                result = retry_with_backoff(
                    lambda: provider.fetch_history(
                        location.latitude,
                        location.longitude,
                        location.country,
                        start,
                        end,
                    )
                )
                provider_circuit_breaker.record_success()
                return result
            except Exception as error:  # noqa: BLE001
                provider_circuit_breaker.record_failure()
                provider_errors.append(f"{provider.provider_name}: {error}")
                LOGGER.warning("Provider failed %s: %s",
                               provider.provider_name, error)

        raise RuntimeError("No provider available: " +
                           " | ".join(provider_errors))
