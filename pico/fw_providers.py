# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
from providers.ci_api import CiApiProvider
from providers.co2signal import Co2SignalProvider
from providers.electricity_maps import ElectricityMapsProvider
from providers.entsoe import EntsoeProvider
from providers.ukci import UkciProvider
from providers.watttime import WattTimeProvider
from utils import ProviderError

# The documented order (docs/architecture.md), and the name each provider is
# reported under in /status and the window payload. Whether a provider is the
# configured one is its own `is_enabled` answer: the enabled switch plus
# whatever credentials or mapping it needs lives next to the code that uses
# them, so adding a provider is a line here and nothing else.
_PROVIDERS = (
    ("uk", UkciProvider),
    ("ci_api", CiApiProvider),
    ("em", ElectricityMapsProvider),
    ("co2signal", Co2SignalProvider),
    ("watttime", WattTimeProvider),
    ("entsoe", EntsoeProvider),
)


def _select(country_code):
    """The one configured provider, as (name, instance)."""
    cc = (country_code or "XX").upper()
    enabled = []
    for name, cls in _PROVIDERS:
        provider = cls()
        if provider.is_enabled(cc):
            enabled.append((name, provider))
    if len(enabled) > 1:
        raise ProviderError("Enable only one provider at a time: %s" % ",".join(name for name, _ in enabled))
    if not enabled:
        raise ProviderError("No providers available")
    return enabled[0]


def selected_provider(country_code):
    return _select(country_code)[0]


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    name, provider = _select(country_code)
    history = provider.fetch_history(lat, lon, country_code, start_epoch, end_epoch)
    return history, name
