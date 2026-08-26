"""Runtime settings from a file on the Pico, instead of literals in source.

Every secret the firmware needs — the Wi-Fi password, each provider token —
used to be an empty string in `config.py` with a `CHANGE ME` beside it. That
means flashing the device requires editing tracked source, and edited source is
one careless `git add` away from committing a credential. It also means a
`git pull` silently reverts the device's configuration.

So the values live in `settings.json` on the device filesystem, which is
gitignored, and `settings.example.json` is the committed template. The defaults
in `config.py` stay exactly as they are and describe the *shape*; the file
overlays them.

Two rules:

**A missing required value fails at startup, by name.** Falling back silently
produces a device that boots, connects to nothing, and shows a dummy reading —
which looks like a bug in the provider rather than an empty password.

**Only known settings are applied.** A typo in the file is reported rather than
silently ignored, because a setting that looks applied and is not is the worst
of the three outcomes.

No MicroPython-only imports, so this is testable under CPython — the same
reason `timeutil.py` sits apart from `utils.py`.
"""

import json

DEFAULT_PATH = "settings.json"


class SettingsError(Exception):
    """A settings file that cannot be used as written."""


def load(path=DEFAULT_PATH, opener=open):
    """Read the settings file. A missing file is {}, not an error.

    Absent is a legitimate state — the defaults in config.py are enough to boot
    a device pointed at a keyless provider. Malformed is not: a file someone
    wrote and got wrong must not be skipped in silence.
    """
    try:
        with opener(path) as fh:
            text = fh.read()
    except OSError:
        return {}
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError as err:
        raise SettingsError("%s is not valid JSON: %s" % (path, err))
    if not isinstance(data, dict):
        raise SettingsError("%s must contain a JSON object" % path)
    return data


def flatten(data, prefix=""):
    """{"wifi": {"ssid": "x"}} -> {"wifi.ssid": "x"}."""
    out = {}
    for key, value in data.items():
        name = "%s.%s" % (prefix, key) if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, name))
        else:
            out[name] = value
    return out


def _resolve(root, dotted):
    """Walk `a.b.c` down the CONFIG class tree, returning (owner, attribute)."""
    parts = dotted.split(".")
    node = root
    for part in parts[:-1]:
        node = getattr(node, part, None)
        if node is None:
            return None, parts[-1]
    return node, parts[-1]


def apply(root, data, path=DEFAULT_PATH):
    """Overlay the file onto the CONFIG tree. Returns the names applied.

    A setting with no matching attribute is an error naming the setting: it is
    almost always a typo, and the alternative is a device that ignores half its
    configuration without saying which half.
    """
    applied, unknown = [], []
    for dotted, value in sorted(flatten(data).items()):
        owner, attr = _resolve(root, dotted)
        if owner is None or not hasattr(owner, attr):
            unknown.append(dotted)
            continue
        setattr(owner, attr, value)
        applied.append(dotted)
    if unknown:
        raise SettingsError(
            "%s sets unknown option(s): %s" % (path, ", ".join(unknown))
        )
    return applied


def require(root, names, path=DEFAULT_PATH):
    """Fail, naming the settings that are missing or empty.

    One error listing every missing value, not one per boot attempt: someone
    filling in a fresh device wants the whole list at once.
    """
    missing = []
    for dotted in names:
        owner, attr = _resolve(root, dotted)
        value = getattr(owner, attr, None) if owner is not None else None
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(dotted)
    if missing:
        raise SettingsError(
            "%s is missing required value(s): %s — copy settings.example.json "
            "to %s and fill them in" % (path, ", ".join(missing), path)
        )


def required_names(root):
    """What must be set, given which providers are enabled.

    Wi-Fi is always required. A provider's credentials are required only when
    that provider is switched on, so a device using the keyless ci-api needs no
    token at all — demanding one would be a fallback of a different kind.
    """
    names = ["wifi.ssid", "wifi.password"]
    providers = getattr(root, "providers", None)
    if providers is None:
        return names
    for attr, needed in (
        ("electricity_maps", ("token",)),
        ("co2signal", ("token",)),
        ("watttime", ("username", "password")),
        ("entsoe", ("token",)),
    ):
        block = getattr(providers, attr, None)
        if block is not None and getattr(block, "enabled", False):
            names.extend("providers.%s.%s" % (attr, field) for field in needed)
    return names
