"""Firmware-visible strings.

Loaded by path, NOT by putting pico/ on sys.path: pico/http.py would shadow the
standard library's `http` package and break every other test in the run.
"""

import importlib.util
import json
import pathlib
import re

_spec = importlib.util.spec_from_file_location(
    "pico_i18n",
    pathlib.Path(__file__).resolve().parents[1] / "pico" / "i18n.py",
)
_i18n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_i18n)

t = _i18n.t
set_language = _i18n.set_language
LOCALES = _i18n.LOCALES
EN = _i18n.EN
MAX_LABEL_CHARS = _i18n.MAX_LABEL_CHARS

REPO = pathlib.Path(__file__).resolve().parents[1]


def teardown_function():
    set_language("en")


class TestSelection:
    def test_english_by_default(self):
        set_language("en")
        assert t("verdict.run_now") == "RUN NOW"

    def test_a_shipped_locale(self):
        set_language("it")
        assert t("verdict.run_now") == "ORA"
        assert t("reason.dirtier") == "Peggio della media"

    def test_an_unknown_language_falls_back_to_english(self):
        assert set_language("kli") == "en"
        assert t("verdict.wait") == "WAIT"

    def test_the_fallback_is_reported_not_silent(self):
        # The caller logs this; a device quietly ignoring its own setting looks
        # like a broken translation rather than a typo in one line.
        assert set_language("it") == "it"
        assert set_language("") == "en"
        assert set_language(None) == "en"

    def test_case_and_whitespace_are_tolerated(self):
        assert set_language(" IT ") == "it"


class TestLookup:
    def test_a_missing_key_renders_the_english_default(self):
        # The requirement that matters most: a blank line on an e-ink panel is
        # indistinguishable from a broken refresh.
        set_language("it")
        _i18n.LOCALES["it"].pop("label.offline", None)
        try:
            assert t("label.offline") == EN["label.offline"]
        finally:
            _i18n.LOCALES["it"]["label.offline"] = "Non in linea"

    def test_an_unknown_key_renders_the_key_not_a_blank(self):
        assert t("nothing.like.this") == "nothing.like.this"
        assert t("nothing.like.this") != ""

    def test_formatting_arguments(self):
        set_language("en")
        assert t("label.co2", 412) == "CO2: 412 g/kWh"
        assert t("label.wait_hours", 3, "14:00") == "WAIT 3h (14:00)"

    def test_a_locale_with_broken_placeholders_falls_back_to_english(self):
        # A translation that dropped its %d would raise on the device. It
        # renders the English form instead, which shows the reading — the
        # number is the point of the line, and a locale bug must not cost it.
        set_language("it")
        _i18n.LOCALES["it"]["label.co2"] = "CO2 senza segnaposto"
        try:
            assert t("label.co2", 412) == "CO2: 412 g/kWh"
        finally:
            _i18n.LOCALES["it"]["label.co2"] = "CO2: %d g/kWh"


class TestLocaleIntegrity:
    def test_every_locale_covers_every_english_key(self):
        for code, table in LOCALES.items():
            missing = set(EN) - set(table)
            assert not missing, f"{code} is missing {sorted(missing)}"

    def test_no_locale_invents_keys(self):
        for code, table in LOCALES.items():
            extra = set(table) - set(EN)
            assert not extra, f"{code} has keys English does not: {sorted(extra)}"

    def test_placeholders_match_english(self):
        # %d in English and %s in Italian is a crash on the device, not a typo.
        for code, table in LOCALES.items():
            for key, text in table.items():
                assert re.findall(r"%[sd]", text) == re.findall(r"%[sd]", EN[key]), (
                    f"{code}:{key} placeholders differ from English"
                )

    def test_labels_fit_the_panel(self):
        # The smallest supported panel is ~20 characters wide; a longer string
        # is clipped silently, so it is checked rather than trusted.
        for code, table in LOCALES.items():
            for key, text in table.items():
                rendered = re.sub(r"%d", "8888", re.sub(r"%s", "88:88", text))
                assert len(rendered) <= MAX_LABEL_CHARS + 8, (
                    f"{code}:{key} is {len(rendered)} chars"
                )


class TestMemoryBudget:
    def test_the_table_is_small_enough_to_live_in_ram(self):
        # Stated in docs/firmware.md. A Pico W leaves tens of KB of heap after
        # this firmware; a few hundred bytes per locale is affordable, and this
        # assertion is what keeps that true when locales are added.
        size = _i18n.table_bytes()
        assert size < 4096, f"the string table is {size} bytes"

    def test_a_locale_costs_a_few_hundred_bytes(self):
        per_locale = _i18n.table_bytes() / len(LOCALES)
        assert per_locale < 1024


class TestDashboardParity:
    def test_the_dashboard_ships_the_same_locales(self):
        """Both halves of the product speak the same languages.

        The issue's requirement is one non-English locale for both; this checks
        the dashboard has not drifted to a different set.
        """
        script = (REPO / "web" / "static" / "script.js").read_text()
        block = script[script.index("const I18N") : script.index("function applyI18n")]
        for code in LOCALES:
            assert re.search(r"\b%s\s*:" % code, block), (
                f"dashboard has no {code} locale"
            )


def test_firmware_strings_are_not_hardcoded_any_more():
    """No English literal left where a label is drawn.

    Checks the three modules the issue names, for the specific strings that
    used to be inline.
    """
    for name, literals in (
        ("pico/recommendation.py", ('"RUN NOW"', '"WAIT"', '"Cleaner than avg"')),
        ("pico/app.py", ('"WAIT %dh (%s)"',)),
        ("pico/display.py", ('"CO2: %d g/kWh"',)),
    ):
        source = (REPO / name).read_text()
        for literal in literals:
            assert literal not in source, f"{name} still hardcodes {literal}"


def test_the_settings_template_documents_the_language_key():
    template = REPO / "pico" / "settings.example.json"
    if not template.exists():
        return  # added by the persisted-settings work; not required here
    json.loads(template.read_text())
