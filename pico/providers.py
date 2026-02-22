
# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
from pico.providers.provider_electricity_maps import fetch_em_past_range
from pico.providers.provider_ukci import fetch_uk_ci_window
from pico.providers.provider_entsoe import ENTSOE_DOMAIN, fetch_entsoe_window
from pico.providers.provider_watttime import fetch_watttime_window
from pico.utils import ProviderError, safe_float


def selected_provider(country_code):
    global CONFIG
    cc = (country_code or "XX").upper()
    entsoe_cc = (CONFIG.providers.entsoe.area_override or cc).upper()

    enabled = []
    if CONFIG.providers.ukci_enabled:
        enabled.append("uk")

    if CONFIG.providers.electricity_maps.enabled and CONFIG.providers.electricity_maps.token:
        enabled.append("em")

    if (
        CONFIG.providers.watttime.enabled
        and CONFIG.providers.watttime.username
        and CONFIG.providers.watttime.password
    ):
        enabled.append("watttime")

    if (
        CONFIG.providers.entsoe.enabled
        and CONFIG.providers.entsoe.token
        and entsoe_cc in ENTSOE_DOMAIN
    ):
        enabled.append("entsoe")

    if len(enabled) > 1:
        raise ProviderError("Enable only one provider at a time: %s" % ",".join(enabled))
    if not enabled:
        raise ProviderError("No providers available")
    return enabled[0]


def _parse_provider_history(points, datetime_key, intensity_getter):
    history = []
    for point in points:
        point_time = point.get(datetime_key)
        value = safe_float(intensity_getter(point))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    provider = selected_provider(country_code)

    if provider == "uk":
        return fetch_uk_ci_window(start_epoch, end_epoch), "uk"
    if provider == "em":
        return fetch_em_past_range(lat, lon, start_epoch, end_epoch), "em"
    if provider == "watttime":
        return fetch_watttime_window(lat, lon, start_epoch, end_epoch), "watttime"
    if provider == "entsoe":
        return fetch_entsoe_window(country_code, start_epoch, end_epoch), "entsoe"

    raise ProviderError("Unknown provider: %s" % provider)

