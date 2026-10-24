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
        ci_api=ns(enabled=False, country_override="", zone="", base_url="https://ci.test"),
        electricity_maps=ns(enabled=False, token="", base_url="https://em.test"),
        co2signal=ns(enabled=False, token=""),
        watttime=ns(enabled=False, username="", password=""),
        entsoe=ns(enabled=False, token="", area_override=""),
        force="",
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


def _credentials(providers, name):
    """What each provider needs to make a request, without switching it on."""
    if name == "em":
        providers.electricity_maps.token = "t"
    elif name == "co2signal":
        providers.co2signal.token = "t"
    elif name == "watttime":
        providers.watttime.username = "u"
        providers.watttime.password = "p"
    elif name == "entsoe":
        providers.entsoe.token = "t"


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


# ---- providers.force ----

ALL = ["uk", "ci_api", "em", "co2signal", "watttime", "entsoe"]


@pytest.mark.parametrize("name", ALL)
def test_force_selects_a_provider_whose_enabled_flag_is_off(selection, name):
    module, providers = selection
    _credentials(providers, name)
    providers.force = name

    assert module._select("IT")[0] == name


@pytest.mark.parametrize("name", ALL)
def test_force_wins_over_another_enabled_provider(selection, name):
    module, providers = selection
    _credentials(providers, name)
    other = "ci_api" if name != "ci_api" else "uk"
    _enable(providers, other)
    providers.force = name

    assert module._select("IT")[0] == name


@pytest.mark.parametrize(
    ("name", "named"),
    [
        ("em", "providers.electricity_maps.token"),
        ("co2signal", "providers.co2signal.token"),
        ("watttime", "providers.watttime.username, providers.watttime.password"),
        ("entsoe", "providers.entsoe.token"),
    ],
)
def test_forcing_a_provider_without_credentials_fails_by_name(selection, name, named):
    module, providers = selection
    # Another provider is fully configured: a forced one must not fall through.
    _enable(providers, "ci_api")
    providers.force = name

    with pytest.raises(ProviderError) as error:
        module._select("IT")

    assert str(error.value) == f"providers.force is {name}, which needs {named}"


def test_forcing_entsoe_for_an_unmapped_area_fails_by_name(selection):
    module, providers = selection
    _credentials(providers, "entsoe")
    providers.force = "entsoe"

    with pytest.raises(ProviderError, match=r"ZZ is not an ENTSO-E area"):
        module._select("ZZ")


def test_forcing_an_unknown_name_lists_the_known_ones(selection):
    module, providers = selection
    providers.force = "nope"

    with pytest.raises(ProviderError, match=r"names no provider: nope \(one of uk, ci_api, em, .*dummy\)"):
        module._select("IT")


def test_force_is_trimmed_and_case_insensitive(selection):
    module, providers = selection
    providers.force = "  CI_API "

    assert module.forced() == "ci_api"
    assert module._select("IT")[0] == "ci_api"


def test_misconfiguration_still_errors_when_nothing_is_forced(selection):
    module, providers = selection
    _enable(providers, "ci_api")
    _enable(providers, "uk")

    with pytest.raises(ProviderError, match="Enable only one provider at a time: uk,ci_api"):
        module._select("IT")


class PastTheGuardError(Exception):
    pass


@pytest.mark.parametrize(
    ("cls", "first_call"),
    [("ElectricityMapsProvider", "http_get_json"), ("CiApiProvider", "utc_offset_now")],
)
def test_the_request_time_guard_checks_credentials_not_the_enabled_flag(selection, cls, first_call):
    # A forced provider has its enabled flag off; the fetch must not refuse it
    # for that. Reaching the first network-side call proves the guard passed.
    module, providers = selection
    _credentials(providers, "em")
    provider_cls = getattr(module, cls)
    provider_cls.fetch_history.__globals__[first_call] = mock.MagicMock(side_effect=PastTheGuardError)

    with pytest.raises(PastTheGuardError):
        provider_cls().fetch_history(41.9, 12.5, "IT", 0, 3600)


def test_the_request_time_guard_still_names_missing_credentials(selection):
    module, _ = selection

    with pytest.raises(ProviderError, match=r"Electricity Maps needs providers\.electricity_maps\.token"):
        module.ElectricityMapsProvider().fetch_history(41.9, 12.5, "IT", 0, 3600)


@pytest.fixture
def app(selection):
    module, providers = selection
    config = types.SimpleNamespace(
        CONFIG=types.SimpleNamespace(
            providers=providers,
            defaults=types.SimpleNamespace(latitude=41.9, longitude=12.5, city="Rome", country="IT"),
            cache_refresh_seconds=3600,
        ),
    )
    stubs = {
        name: mock.MagicMock()
        for name in (
            "diagnostics",
            "export",
            "fetcher",
            "recommendation",
            "timeutil",
            "ttl_cache",
            "uptime",
            "utils",
        )
    }
    stubs.update({"config": config, "fw_providers": module})
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("pico_app_under_test", PICO / "app.py")
        app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_module)
    london = {"lat": 51.5, "lon": -0.13, "city": "London", "cc": "GB"}
    app_module._auto_geo_defaults = lambda: london
    return app_module, providers


def test_forcing_a_provider_forces_the_configured_city(app):
    module, providers = app

    assert module.resolve_geo({}) == (51.5, -0.13, "London", "GB")

    providers.force = "ci_api"
    assert module.resolve_geo({}) == (41.9, 12.5, "Rome", "IT")


def test_force_dummy_is_the_simulated_series(app):
    module, providers = app
    providers.force = "dummy"
    module.dummy_fetch_window_any = mock.MagicMock(return_value=({"history": []}, "dummy"))
    module.fetch_window_any = mock.MagicMock()

    data = module._fetch_window(41.9, 12.5, "Rome", "IT", 0, 3600)

    assert data["_provider"] == "dummy"
    module.fetch_window_any.assert_not_called()


def test_no_force_fetches_from_the_selected_provider(app):
    module, _ = app
    module.dummy_fetch_window_any = mock.MagicMock()
    module.fetch_window_any = mock.MagicMock(return_value=({"history": []}, "ci_api"))

    assert module._fetch_window(41.9, 12.5, "Rome", "IT", 0, 3600)["_provider"] == "ci_api"
    module.dummy_fetch_window_any.assert_not_called()
