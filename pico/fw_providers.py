# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
from providers.ci_api import CiApiProvider
from providers.co2signal import Co2SignalProvider
from providers.electricity_maps import ElectricityMapsProvider
from providers.entsoe import EntsoeProvider
from providers.ukci import UkciProvider
from providers.watttime import WattTimeProvider
from settings import forced_name
from utils import ProviderError

from config import CONFIG

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


# `providers.force = "dummy"` is the simulated series app.py generates; it
# never reaches _select.
FORCE_DUMMY = "dummy"


def forced():
    """The provider name `providers.force` asks for, or "" when it is unset."""
    return forced_name(CONFIG.providers.force)


def _forced_provider(name, cc):
    """The provider `providers.force` names, whatever its `enabled` flag says.

    Testing aid: point the device at a grid it is not in without editing the
    enabled flags. A forced provider without its credentials fails by name
    rather than falling through to another one, which would show readings from
    a provider nobody asked for.
    """
    cls = dict(_PROVIDERS).get(name)
    if cls is None:
        known = [candidate for candidate, _ in _PROVIDERS] + [FORCE_DUMMY]
        raise ProviderError("providers.force names no provider: %s (one of %s)" % (name, ", ".join(known)))
    provider = cls()
    missing = provider.missing(cc)
    if missing:
        raise ProviderError("providers.force is %s, which needs %s" % (name, ", ".join(missing)))
    return name, provider


def _select(country_code):
    """The one configured provider, as (name, instance)."""
    cc = (country_code or "XX").upper()
    name = forced()
    if name:
        return _forced_provider(name, cc)
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
