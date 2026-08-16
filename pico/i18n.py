"""Firmware-visible strings, in the language the device is configured for.

The dashboard resolves `data-i18n` keys in `web/static/script.js`; the firmware
had its labels inline in English, so half the product was translated and the
half on the physical display — the part a non-English speaker actually looks at
— was not.

Three constraints shape this rather than a general i18n library:

**A missing key renders the English default, never blank.** A blank line on an
e-ink panel is indistinguishable from a broken refresh, and the panel is the
only output some installs have.

**The table has to fit.** These strings live in RAM for the life of the
process. The whole table is measured by a test, and the budget is stated in
docs/firmware.md — a locale is a few hundred bytes, which is affordable, and
this stays true only while nobody adds prose to it.

**Strings must fit the panel.** The display is 122 px wide in the smallest
supported panel, which is about 20 characters at the built-in font. A
translation that overflows is silently clipped, so the test checks length
rather than trusting the translator.

No MicroPython-only imports, so this is testable under CPython.
"""

# English is the source of truth: every other locale is checked against its
# keys, and any key missing from a locale falls back to the entry here.
EN = {
    # Verdicts — the largest text on the panel.
    "verdict.run_now": "RUN NOW",
    "verdict.ok": "OK",
    "verdict.wait": "WAIT",
    # Reasons, shown under the verdict.
    "reason.cleaner": "Cleaner than avg",
    "reason.average": "Around average",
    "reason.dirtier": "Dirtier than avg",
    # Labels and units.
    "label.now": "Now",
    "label.co2": "CO2: %d g/kWh",
    "label.wait_hours": "WAIT %dh (%s)",
    "label.no_data": "No data",
    "label.offline": "Offline",
    "label.updating": "Updating...",
}

IT = {
    "verdict.run_now": "ORA",
    "verdict.ok": "OK",
    "verdict.wait": "ATTENDI",
    "reason.cleaner": "Meglio della media",
    "reason.average": "Nella media",
    "reason.dirtier": "Peggio della media",
    "label.now": "Ora",
    "label.co2": "CO2: %d g/kWh",
    "label.wait_hours": "ATTENDI %dh (%s)",
    "label.no_data": "Nessun dato",
    "label.offline": "Non in linea",
    "label.updating": "Aggiorno...",
}

LOCALES = {"en": EN, "it": IT}

# The smallest supported panel is 122 px wide and the built-in font is 8 px per
# character, so anything past this is clipped rather than wrapped.
MAX_LABEL_CHARS = 20

_active = EN


def set_language(code):
    """Select a locale. An unknown code falls back to English.

    Returns the code actually in use, so the caller can log the fallback rather
    than have a device quietly ignore its own configuration.
    """
    global _active
    code = (code or "en").strip().lower()
    _active = LOCALES.get(code, EN)
    return code if code in LOCALES else "en"


def t(key, *args):
    """The string for `key` in the active locale.

    Falls back to English, then to the key itself. The key is a poor label but
    it is visible and searchable, which a blank line is not.
    """
    text = _active.get(key)
    if text is None:
        text = EN.get(key, key)
    if args:
        try:
            return text % args
        except (TypeError, ValueError):
            # A locale whose placeholders do not match the call must not take
            # the display down: fall back to the English form.
            fallback = EN.get(key, key)
            try:
                return fallback % args
            except (TypeError, ValueError):
                return fallback
    return text


def table_bytes():
    """Rough in-RAM size of every locale, for the memory budget test."""
    total = 0
    for locale in LOCALES.values():
        for key, value in locale.items():
            total += len(key) + len(value) + 2
    return total
