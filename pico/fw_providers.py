# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
from providers.ci_api import CiApiProvider
from providers.co2signal import Co2SignalProvider
from providers.electricity_maps import ElectricityMapsProvider
from providers.entsoe import ENTSOE_DOMAIN, EntsoeProvider
from providers.ukci import UkciProvider
from providers.watttime import WattTimeProvider
from utils import ProviderError

from config import CONFIG


# TODO: Refactor to use is_enabled
def _select(country_code):
    """The one configured provider, as (name, class).

    One table rather than one `if` per provider in two places: the name and the
    class it dispatches to were listed separately, so adding a provider meant
    editing both lists and forgetting one meant a silent "Unknown provider".
    Order is the documented fallback order (docs/architecture.md).

    The middle column is everything that has to be true for that provider to be
    the configured one — the enabled switch and whatever credentials it needs.
    `all` over the tuple is what the chained `and`s used to say.
    """
    cc = (country_code or "XX").upper()
    entsoe_cc = (CONFIG.providers.entsoe.area_override or cc).upper()
    providers = CONFIG.providers

    candidates = (
        ("uk", (providers.ukci_enabled,), UkciProvider),
        # No token to check: the API is keyless.
        ("ci_api", (providers.ci_api.enabled,), CiApiProvider),
        (
            "em",
            (providers.electricity_maps.enabled, providers.electricity_maps.token),
            ElectricityMapsProvider,
        ),
        (
            "co2signal",
            (providers.co2signal.enabled, providers.co2signal.token),
            Co2SignalProvider,
        ),
        (
            "watttime",
            (
                providers.watttime.enabled,
                providers.watttime.username,
                providers.watttime.password,
            ),
            WattTimeProvider,
        ),
        (
            "entsoe",
            (
                providers.entsoe.enabled,
                providers.entsoe.token,
                entsoe_cc in ENTSOE_DOMAIN,
            ),
            EntsoeProvider,
        ),
    )

    enabled = [(name, cls) for name, required, cls in candidates if all(required)]
    if len(enabled) > 1:
        raise ProviderError(
            "Enable only one provider at a time: %s"
            % ",".join(name for name, _ in enabled)
        )
    if not enabled:
        raise ProviderError("No providers available")
    return enabled[0]


def selected_provider(country_code):
    return _select(country_code)[0]


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    provider, provider_class = _select(country_code)
    history = provider_class().fetch_history(
        lat, lon, country_code, start_epoch, end_epoch
    )
    return history, provider
