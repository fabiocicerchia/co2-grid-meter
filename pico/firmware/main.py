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
from pico.firmware.fw_config import CONFIG, append_log_line, build_firmware_logger, write_crashdump
from pico.firmware.fw_network import wifi_connect
from pico.firmware.fw_http import serve_forever, set_time

# =========================
# main
# =========================

LOGGER = None
def main():
    LOGGER = build_firmware_logger()

    gc.enable()
    connected, ip = wifi_connect()
    
    if not connected:
        CONFIG.wifi.ssid = "" # CHANGE ME
        CONFIG.wifi.password = "" # CHANGE ME
        connected, ip = wifi_connect()
    
    if connected:
        set_time(2) # ITALY GMT+1 # TODO: FIX DAYLIGHT
        
    serve_forever(ip)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        crash_path = write_crashdump(error, context="http")
        LOGGER.exception("ERROR", error, crash_path)
        append_log_line("ERROR %s" % crash_path)
