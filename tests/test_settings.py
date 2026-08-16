"""Persisted device settings, replacing the CHANGE ME literals.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.
"""

import importlib.util
import io
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "pico_settings",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "settings.py",
)
_settings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_settings)

SettingsError = _settings.SettingsError
load = _settings.load
apply = _settings.apply
require = _settings.require
required_names = _settings.required_names
flatten = _settings.flatten

TEMPLATE = (
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "settings.example.json"
)


def fake_config():
    """A stand-in with the same shape as CONFIG, so tests need no MicroPython."""

    class C:
        class wifi:
            ssid = ""
            password = ""

        class defaults:
            city = "Rome"
            utc_offset_hours = 1

        class providers:
            class ci_api:
                enabled = False
                zone = ""

            class electricity_maps:
                enabled = False
                token = ""

            class watttime:
                enabled = False
                username = ""
                password = ""

            class entsoe:
                enabled = False
                token = ""

    return C


def opener_for(text):
    def _open(_path):
        return io.StringIO(text)

    return _open


class TestLoad:
    def test_a_missing_file_is_empty_not_an_error(self):
        def missing(_path):
            raise OSError("no such file")

        assert load("settings.json", opener=missing) == {}

    def test_an_empty_file_is_empty(self):
        assert load("settings.json", opener=opener_for("   \n")) == {}

    def test_malformed_json_is_reported_not_skipped(self):
        # A file someone wrote and got wrong must not be ignored in silence.
        with pytest.raises(SettingsError) as err:
            load("settings.json", opener=opener_for("{nope"))
        assert "settings.json" in str(err.value)

    def test_a_json_array_is_refused(self):
        with pytest.raises(SettingsError):
            load("settings.json", opener=opener_for("[1, 2]"))


class TestApply:
    def test_nested_values_reach_the_config_tree(self):
        cfg = fake_config()
        apply(
            cfg,
            {
                "wifi": {"ssid": "home", "password": "hunter2"},
                "providers": {"entsoe": {"enabled": True, "token": "t"}},
            },
        )
        assert cfg.wifi.ssid == "home"
        assert cfg.providers.entsoe.enabled is True
        assert cfg.providers.entsoe.token == "t"

    def test_omitted_values_keep_their_defaults(self):
        cfg = fake_config()
        apply(cfg, {"wifi": {"ssid": "home"}})
        assert cfg.defaults.city == "Rome"
        assert cfg.wifi.password == ""

    def test_an_unknown_setting_is_an_error_naming_it(self):
        # Almost always a typo. Ignoring it silently gives a device that drops
        # half its configuration without saying which half.
        cfg = fake_config()
        with pytest.raises(SettingsError) as err:
            apply(cfg, {"wifi": {"sid": "home"}})
        assert "wifi.sid" in str(err.value)

    def test_flatten(self):
        assert flatten({"a": {"b": 1}, "c": 2}) == {"a.b": 1, "c": 2}


class TestRequire:
    def test_missing_wifi_fails_by_name(self):
        cfg = fake_config()
        with pytest.raises(SettingsError) as err:
            require(cfg, required_names(cfg))
        assert "wifi.ssid" in str(err.value)
        assert "wifi.password" in str(err.value)

    def test_every_missing_value_is_listed_at_once(self):
        cfg = fake_config()
        cfg.providers.entsoe.enabled = True
        with pytest.raises(SettingsError) as err:
            require(cfg, required_names(cfg))
        message = str(err.value)
        for name in ("wifi.ssid", "wifi.password", "providers.entsoe.token"):
            assert name in message

    def test_only_enabled_providers_need_credentials(self):
        # The keyless ci-api needs no token; demanding one would be a fallback
        # of a different kind.
        cfg = fake_config()
        cfg.wifi.ssid, cfg.wifi.password = "home", "pw"
        cfg.providers.ci_api.enabled = True
        require(cfg, required_names(cfg))  # must not raise

    def test_whitespace_is_not_a_value(self):
        cfg = fake_config()
        cfg.wifi.ssid, cfg.wifi.password = "  ", "pw"
        with pytest.raises(SettingsError) as err:
            require(cfg, required_names(cfg))
        assert "wifi.ssid" in str(err.value)

    def test_watttime_needs_both_halves(self):
        cfg = fake_config()
        cfg.wifi.ssid, cfg.wifi.password = "home", "pw"
        cfg.providers.watttime.enabled = True
        cfg.providers.watttime.username = "u"
        with pytest.raises(SettingsError) as err:
            require(cfg, required_names(cfg))
        assert "providers.watttime.password" in str(err.value)


class TestTemplate:
    def test_the_committed_template_parses(self):
        json.loads(TEMPLATE.read_text())

    def test_every_template_key_exists_in_the_real_config(self):
        """The file people copy must not fail the unknown-setting check.

        Checked against pico/config.py itself, read with ast — importing it
        would need pico/ on sys.path, which pico/http.py makes unsafe.
        """
        import ast

        source = (
            pathlib.Path(__file__).resolve().parents[1] / "pico" / "config.py"
        ).read_text()
        tree = ast.parse(source)

        def names_of(node, prefix=""):
            out = set()
            for item in node.body:
                if isinstance(item, ast.ClassDef):
                    inner = f"{prefix}{item.name}."
                    out.add(inner.rstrip("."))
                    out |= names_of(item, inner)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            out.add(prefix + target.id)
            return out

        config_cls = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CONFIG"
        )
        known = names_of(config_cls)

        data = json.loads(TEMPLATE.read_text())
        data.pop("_comment", None)
        for dotted in flatten(data):
            assert dotted in known, f"{dotted} is in the template but not in CONFIG"

    def test_the_template_carries_no_real_credential(self):
        text = TEMPLATE.read_text()
        for suspicious in ("ghp_", "sk-", "AKIA", "-----BEGIN"):
            assert suspicious not in text
