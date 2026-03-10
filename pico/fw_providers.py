# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
from providers.electricity_maps import ElectricityMapsProvider
from providers.ukci import UkciProvider
from providers.entsoe import ENTSOE_DOMAIN, EntsoeProvider
from providers.watttime import WattTimeProvider
from providers.co2signal import Co2SignalProvider
from utils import ProviderError
from config import CONFIG


# TODO: Refactor to use is_enabled
def selected_provider(country_code):
    cc = (country_code or "XX").upper()
    entsoe_cc = (CONFIG.providers.entsoe.area_override or cc).upper()

    enabled = []
    if CONFIG.providers.ukci_enabled:
        enabled.append("uk")

    if (
        CONFIG.providers.electricity_maps.enabled
        and CONFIG.providers.electricity_maps.token
    ):
        enabled.append("em")

    if CONFIG.providers.co2signal.enabled and CONFIG.providers.co2signal.token:
        enabled.append("co2signal")

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
        raise ProviderError(
            "Enable only one provider at a time: %s" % ",".join(enabled)
        )
    if not enabled:
        raise ProviderError("No providers available")
    return enabled[0]


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    provider = selected_provider(country_code)

    providerClass = ""

    if provider == "uk":
        providerClass = UkciProvider()
    if provider == "em":
        providerClass = ElectricityMapsProvider()
    if provider == "co2signal":
        providerClass = Co2SignalProvider()
    if provider == "watttime":
        providerClass = WattTimeProvider()
    if provider == "entsoe":
        providerClass = EntsoeProvider()

    if providerClass != "":
        return (
            providerClass.fetch_history(lat, lon, country_code, start_epoch, end_epoch),
            provider,
        )

    raise ProviderError("Unknown provider: %s" % provider)
