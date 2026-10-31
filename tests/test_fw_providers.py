"""Provider selection asks each provider, and only the provider, if it is on.

`_select` used to decide from its own table of config reads, so every
provider's enablement rule was written twice and the copy in each provider's
`is_enabled` was never called. These tests drive the real provider modules
through `fw_providers._select` with a config object they control, so a rule
that drifts between the two places cannot pass.

The provider modules import `utils` (which pulls in `urequests`) and `config`
(which reads flash), so both are stubbed for the duration of the load. pico/
is on sys.path only while loading: pico/http.py would shadow the standard
library's `http` for the rest of the run.
"""

import importlib.util
import pathlib
import sys
import types
from unittest import mock

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


class ProviderError(RuntimeError):
    pass


def _config():
    ns = types.SimpleNamespace
    return ns(
        ukci_enabled=False,
        ci_api=ns(enabled=False),
        electricity_maps=ns(enabled=False, token=""),
        co2signal=ns(enabled=False, token=""),
        watttime=ns(enabled=False, username="", password=""),
        entsoe=ns(enabled=False, token="", area_override=""),
        force_dummy=False,
    )


@pytest.fixture
def selection():
    providers = _config()
    config = types.SimpleNamespace(
        CONFIG=types.SimpleNamespace(providers=providers),
        FLASH_LOCK=mock.MagicMock(),
    )
    utils = mock.MagicMock()
    utils.ProviderError = ProviderError
    stubs = {
        "config": config,
        "utils": utils,
        "ujson": mock.MagicMock(),
        "urequests": mock.MagicMock(),
        "ubinascii": mock.MagicMock(),
    }
    sys.path.insert(0, str(PICO))
    try:
        with mock.patch.dict(sys.modules, stubs):
            spec = importlib.util.spec_from_file_location("pico_fw_providers", PICO / "fw_providers.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(PICO))
    return module, providers


def _enable(providers, name):
    if name == "uk":
        providers.ukci_enabled = True
    elif name == "ci_api":
        providers.ci_api.enabled = True
    elif name == "em":
        providers.electricity_maps.enabled = True
        providers.electricity_maps.token = "t"
    elif name == "co2signal":
        providers.co2signal.enabled = True
        providers.co2signal.token = "t"
    elif name == "watttime":
        providers.watttime.enabled = True
        providers.watttime.username = "u"
        providers.watttime.password = "p"
    elif name == "entsoe":
        providers.entsoe.enabled = True
        providers.entsoe.token = "t"


@pytest.mark.parametrize("name", ["uk", "ci_api", "em", "co2signal", "watttime", "entsoe"])
def test_each_provider_is_selected_when_it_alone_is_configured(selection, name):
    module, providers = selection
    _enable(providers, name)

    selected, provider = module._select("IT")

    assert selected == name
    assert module.selected_provider("IT") == name
    assert provider.is_enabled("IT") is True


@pytest.mark.parametrize(
    ("name", "missing"),
    [
        ("em", ("electricity_maps", "token")),
        ("co2signal", ("co2signal", "token")),
        ("watttime", ("watttime", "username")),
        ("watttime", ("watttime", "password")),
        ("entsoe", ("entsoe", "token")),
    ],
)
def test_an_enabled_provider_without_its_credentials_is_not_selected(selection, name, missing):
    module, providers = selection
    _enable(providers, name)
    block, field = missing
    setattr(getattr(providers, block), field, "")

    with pytest.raises(ProviderError, match="No providers available"):
        module._select("IT")


def test_entsoe_needs_a_mapped_area(selection):
    module, providers = selection
    _enable(providers, "entsoe")

    with pytest.raises(ProviderError, match="No providers available"):
        module._select("ZZ")

    assert module._select("it")[0] == "entsoe"


def test_entsoe_area_override_wins_over_the_country(selection):
    module, providers = selection
    _enable(providers, "entsoe")

    providers.entsoe.area_override = "IT-CSOUTH"
    assert module._select("ZZ")[0] == "entsoe"

    providers.entsoe.area_override = "NOWHERE"
    with pytest.raises(ProviderError, match="No providers available"):
        module._select("IT")


def test_no_provider_configured_is_an_error(selection):
    module, _ = selection

    with pytest.raises(ProviderError, match="No providers available"):
        module._select("IT")


def test_two_providers_configured_is_an_error_naming_both(selection):
    module, providers = selection
    _enable(providers, "ci_api")
    _enable(providers, "watttime")

    with pytest.raises(ProviderError, match="Enable only one provider at a time: ci_api,watttime"):
        module._select("IT")


def test_fetch_window_any_reports_the_selected_name(selection):
    module, providers = selection
    _enable(providers, "ci_api")

    with mock.patch.object(module.CiApiProvider, "fetch_history", return_value={"history": []}) as fetch:
        history, name = module.fetch_window_any(41.9, 12.5, "Rome", "IT", 0, 3600)

    assert (history, name) == ({"history": []}, "ci_api")
    fetch.assert_called_once_with(41.9, 12.5, "IT", 0, 3600)
