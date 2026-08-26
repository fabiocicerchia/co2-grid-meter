import logging
import os
import sys
import time

# Bare-name import, like every other module under pico/. settings.py imports
# nothing from here, so there is no cycle; only the overlay *call* has to wait
# for CONFIG to exist, and that is at the bottom of the file.
from settings import SettingsError
from settings import apply as _apply_settings
from settings import load as _load_settings
from settings import require as _require_settings
from settings import required_names as _required_settings


class CONFIG:
    """Firmware defaults.

    Secrets are NOT here. Everything in this file is a default that describes
    the shape of the configuration; the device's own values are overlaid from
    settings.json at import (see pico/settings.py), which is gitignored so a
    filled-in device cannot be committed by accident.
    """

    class wifi:
        # Overlaid from settings.json — an empty value here fails at startup
        # with a named error rather than booting into a dummy reading.
        ssid = ""
        password = ""

    class defaults:
        # ENTSOE
        latitude = 41.9028
        longitude = 12.4964
        city = "Rome"
        country = "IT"

        # Local wall-clock time: standard (winter) offset from UTC, plus the
        # EU summer-time rule. Italy and the UK both observe it and change at
        # the same instants; set observes_eu_dst = False for anywhere that
        # does not (UTC, most of Asia).
        utc_offset_hours = 1
        observes_eu_dst = True

        # UKCI
        # latitude = 51.5072
        # longitude = 0.1276
        # city = "London"
        # country = "GB"

        # ELECTRICITY MAP
        # latitude = 59.3327
        # longitude = 18.0656
        # city = "Stockholm"
        # country = "SE"

        # WATTTIME
        # latitude = 37.7749
        # longitude = -122.4194  # west of Greenwich: the sign is load-bearing
        # city = "San Francisco"
        # country = "CAISO_NORTH"

    class web:
        # Serve the dashboard's own files from the device, for an install with
        # no desktop server. Off by default: an existing deployment must not
        # start serving files because it was upgraded, and a device without the
        # assets copied over would answer 404 for every page.
        serve_static = False
        # Where those files live on the Pico's filesystem.
        static_root = "static"

    class providers:
        ukci_enabled = False

        # Keyless, every country, plus bidding zones where the operator
        # publishes them. Last hour only, so the timeline fills in as the
        # device polls.
        class ci_api:
            enabled = False
            base_url = "https://ci-api.fabiocicerchia.it"
            # Empty follows defaults.country; set it to pin the lookup.
            country_override = ""
            # Bidding zone / balancing region within the country — "SICI",
            # "SE3", "TEX", "NSW1". Zone readings carry no consumption figures,
            # so they report `lifecycle` instead of `consumption_lifecycle`.
            zone = ""

        class electricity_maps:
            enabled = False
            token = ""
            base_url = "https://api.electricitymaps.com"

        class co2signal:
            enabled = False
            token = ""
            base_url = "https://api.co2signal.com"

        class watttime:
            enabled = False
            username = ""
            password = ""
            base_url = "https://api.watttime.org"
            # Free WattTime accounts are granted one region (CAISO_NORTH). Set
            # this to pin it and skip the location lookup entirely; leave it
            # empty and the region is resolved from lat/lon, which is what a
            # paid account wants.
            region = ""

        # TODO: it's super slow due to XML response
        class entsoe:
            enabled = True
            token = ""
            base_url = "https://web-api.tp.entsoe.eu/api"
            area_override = "IT-CSOUTH"

        watttime_cooldown_sec = 24 * 3600
        force_dummy = False

    class timeline:
        back_hours_default = 48
        past_hours = 36
        future_hours = 12

    class thresholds:
        green_percentile_max = 0.25
        yellow_percentile_max = 0.50

    class server:
        host = "0.0.0.0"
        port = 8080

    class display:
        render_min_interval_sec = 60
        landscape = True

    class ui:
        # Language for the strings the device renders itself — see pico/i18n.py
        # for the table and what each locale must fit. An unknown code falls
        # back to English and says so in the boot log, rather than leaving the
        # panel blank.
        language = "en"

    class geo:
        auto_from_public_ip = True
        ip_lookup_url = "https://ipwho.is/"
        refresh_seconds = 24 * 3600
        failure_retry_seconds = 15 * 60

    cache_refresh_seconds = 300  # 5 mins


# Simple filesystem persistence helpers for firmware logs/crash dumps.

LOG_DIR = "logs"
CRASH_DIR = "crashdumps"


def _safe_mkdir(path: str) -> None:
    try:
        os.mkdir(path)
    except OSError:
        pass


def _ensure_dirs() -> None:
    _safe_mkdir(LOG_DIR)
    _safe_mkdir(CRASH_DIR)


def _date_from_epoch(epoch: int | None = None) -> str:
    ts = time.localtime(epoch or time.time())
    return "%04d-%02d-%02d" % (ts[0], ts[1], ts[2])


def append_log_line(message: str) -> None:
    _ensure_dirs()
    day = _date_from_epoch()
    path = "%s/%s.log" % (LOG_DIR, day)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("[%d] %s\n" % (int(time.time()), message))
    prune_old_logs(days=2)


def prune_old_logs(days: int = 2) -> None:
    _ensure_dirs()
    entries = []
    for name in os.listdir(LOG_DIR):
        if not name.endswith(".log"):
            continue
        full = "%s/%s" % (LOG_DIR, name)
        try:
            mtime = os.stat(full)[8]
            entries.append((mtime, full))
        except OSError:
            continue

    entries.sort(reverse=True)
    for _, full in entries[days:]:
        try:
            os.remove(full)
        except OSError:
            pass


def write_crashdump(error: Exception, context: str = "runtime") -> str:
    _ensure_dirs()
    stamp = int(time.time())
    sys.print_exception(error)
    path = "%s/%s-%d.txt" % (CRASH_DIR, context, stamp)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("timestamp=%d\n" % stamp)
        handle.write("context=%s\n" % context)
        handle.write("error=%s\n" % str(error))
    return path


class _DailyFileLogHandler(logging.Handler):
    def emit(self, record):
        try:
            message = self.format(record)
            append_log_line(message)
        except Exception:
            pass


# --- settings.json overlay ---------------------------------------------------
# Applied at import so every module that does `from config import CONFIG` sees
# the device's own values, not the defaults above. Import-time failure is
# deliberate: a device that boots with no Wi-Fi password shows a dummy reading,
# which reads as a broken provider rather than an empty setting.
SETTINGS_ERROR = None
try:
    _apply_settings(CONFIG, _load_settings())
    _require_settings(CONFIG, _required_settings(CONFIG))
except SettingsError as _err:
    # Held rather than raised here: main.py reports it in one place, with the
    # crash-dump handling the rest of the boot already has.
    SETTINGS_ERROR = str(_err)


def build_firmware_logger(name: str = "pico.firmware"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )

    file_handler = _DailyFileLogHandler()
    file_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger
