"""Single-file Pico firmware bundle.

This file is provided so you can copy/paste one script to the device.
It inlines the behavior from the `pico/firmware/*` modules and keeps the
same HTTP API:
- GET /
- GET /status
- GET /em/window
- GET /em/window-overlay
"""

# =========================
# Runtime imports / fallbacks
# =========================

import gc
import sys
from http import serve_forever, set_time

from fw_network import wifi_connect
from uptime import UPTIME

from config import SETTINGS_ERROR as CONFIG_SETTINGS_ERROR
from config import append_log_line, build_firmware_logger, write_crashdump

# =========================
# main
# =========================

LOGGER = None


def main():
    global LOGGER
    LOGGER = build_firmware_logger()

    # Settings are read at import; a problem with them is reported here, by
    # name, before anything tries to use a value that is not there.
    if CONFIG_SETTINGS_ERROR:
        LOGGER.info("FATAL: %s" % CONFIG_SETTINGS_ERROR)
        raise SystemExit(CONFIG_SETTINGS_ERROR)

    gc.enable()
    connected, ip = wifi_connect()

    if not connected:
        # One retry: the radio is often not up on the first attempt after a
        # cold boot. Blanking the credentials here (as this used to) guaranteed
        # the retry failed.
        connected, ip = wifi_connect()

    if connected:
        set_time()  # local time from CONFIG.defaults, EU summer time included

    # After the network, before serving: the diagnostics are most useful in the
    # log above the first request, not interleaved with it.
    try:
        from app import log_boot_diagnostics

        log_boot_diagnostics()
    except Exception as error:  # diagnostics must never stop the device serving
        LOGGER.info("Diagnostics unavailable: %s" % error)

    # Logged after the network, so the line lands in whatever the logger is
    # actually writing to. Reads 0s on a fresh boot, which is the point: it is
    # how you tell a reboot loop from a device that has been up for days.
    LOGGER.info("Uptime at start of serving: %s" % UPTIME.human())

    serve_forever(ip, LOGGER)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.print_exception(error)
        crash_path = write_crashdump(error, context="http")
        append_log_line("ERROR %s" % crash_path)
