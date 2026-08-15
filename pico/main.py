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
from i18n import set_language

from config import CONFIG, append_log_line, build_firmware_logger, write_crashdump

# =========================
# main
# =========================

LOGGER = None


def main():
    global LOGGER
    LOGGER = build_firmware_logger()

    # Before anything renders: the panel's strings are resolved through the
    # table, and a device that ignored its own language setting would look like
    # a broken translation rather than a typo in one line.
    selected = set_language(CONFIG.ui.language)
    if selected != CONFIG.ui.language:
        LOGGER.info("Unknown language %r, using %s" % (CONFIG.ui.language, selected))

    gc.enable()
    connected, ip = wifi_connect()

    if not connected:
        CONFIG.wifi.ssid = ""  # CHANGE ME
        CONFIG.wifi.password = ""  # CHANGE ME
        connected, ip = wifi_connect()

    if connected:
        set_time()  # local time from CONFIG.defaults, EU summer time included

    serve_forever(ip, LOGGER)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.print_exception(error)
        crash_path = write_crashdump(error, context="http")
        append_log_line("ERROR %s" % crash_path)
