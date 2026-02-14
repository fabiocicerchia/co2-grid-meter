"""Provider orchestration entrypoint for firmware endpoints."""

from pico.fw_providers_utils import provider_order as _provider_order

from fw_provider_electricity_maps import fetch_em_past_range
from fw_provider_ukci import fetch_uk_ci_window
from fw_provider_watttime import fetch_watttime_current

import fw_config
from fw_utils import ProviderError


def provider_order(country_code):
    return _provider_order(fw_config.CONFIG, country_code)


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city  # kept for call signature compatibility

    providers = provider_order(country_code)
    last_error = None

    for provider in providers:
        try:
            if provider == "uk":
                return fetch_uk_ci_window(start_epoch, end_epoch), "uk"
            if provider == "em":
                return fetch_em_past_range(lat, lon, start_epoch, end_epoch), "em"
            if provider == "watttime":
                return fetch_watttime_current(lat, lon), "watttime"
        except Exception as error:
            last_error = error

    raise ProviderError(str(last_error) if last_error else "No providers available")
