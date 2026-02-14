"""Firmware configuration access.

Use `CONFIG` for runtime values. Hardware/display constants below document the
Waveshare WS-19588 wiring/layout used by this firmware.
"""

try:
    from common_config import CONFIG as UNIFIED_CONFIG

    CONFIG = UNIFIED_CONFIG.firmware
except Exception:
    try:
        import os
    except Exception:  # pragma: no cover - MicroPython may expose uos only
        os = None

    def _env(name, default):
        if not os:
            return default
        return os.getenv(name, default)

    class _Wifi:
        ssid = _env("WIFI_SSID", "YOUR_WIFI_SSID")
        password = _env("WIFI_PASS", "YOUR_WIFI_PASSWORD")

    class _Defaults:
        latitude = float(_env("DEFAULT_LAT", "41.9028"))
        longitude = float(_env("DEFAULT_LON", "12.4964"))
        city = _env("DEFAULT_CITY", "Rome")
        country = _env("DEFAULT_CC", "IT")

    class _ElectricityMaps:
        enabled = _env("EM_ENABLED", "0") == "1"
        token = _env("EM_TOKEN", "")
        base_url = _env("EM_BASE", "https://api.electricitymaps.org")

    class _WattTime:
        enabled = _env("WT_ENABLED", "1") == "1"
        username = _env("WATTTIME_USERNAME", "")
        password = _env("WATTTIME_PASSWORD", "")
        base_url = _env("WT_BASE", "https://api.watttime.org")

    class _Providers:
        ukci_enabled = _env("UKCI_ENABLED", "1") == "1"
        electricity_maps = _ElectricityMaps()
        watttime = _WattTime()
        watttime_cooldown_sec = int(_env("WT_COOLDOWN_SEC", str(24 * 3600)))

    class _Timeline:
        back_hours_default = int(_env("BACK_HOURS_DEFAULT", "48"))
        past_hours = int(_env("PAST_HOURS", "36"))
        future_hours = int(_env("FUTURE_HOURS", "12"))
        lookahead_hours = int(_env("LOOKAHEAD_HOURS", "12"))

    class _Thresholds:
        green_percentile_max = float(_env("P_GREEN_MAX", "0.33"))
        yellow_percentile_max = float(_env("P_YELLOW_MAX", "0.66"))

    class _Server:
        host = _env("HOST", "0.0.0.0")
        port = int(_env("PICO_PORT", "8080"))

    class _Display:
        render_min_interval_sec = int(_env("RENDER_MIN_INTERVAL_SEC", "60"))

    class _FirmwareConfig:  # pragma: no cover - executed on device
        wifi = _Wifi()
        defaults = _Defaults()
        providers = _Providers()
        timeline = _Timeline()
        thresholds = _Thresholds()
        server = _Server()
        display = _Display()
        cache_refresh_seconds = int(_env("PICO_CACHE_REFRESH_SECONDS", "3600"))

    CONFIG = _FirmwareConfig()


# WS-19588 panel resolution in pixels (width x height). Tri-color 2.13" panel.
EPD_W = 122
EPD_H = 250

# Framebuffer alignment: framebuf.MONO_HLSB stores 8 horizontal pixels per byte.
FB_W = ((EPD_W + 7) // 8) * 8
FB_H = EPD_H
BYTES_PER_LINE = FB_W // 8
BUF_LEN = BYTES_PER_LINE * FB_H

# SPI bus used in Waveshare's Pico demo for the 2.13" B V4 panel.
SPI_BUS = 1

# Control pins based on Waveshare's reference script:
# RST=12, DC=8, CS=9, BUSY=13.
PIN_SCK = 10   # SPI1 clock (GP10)
PIN_MOSI = 11  # SPI1 MOSI (GP11)
PIN_MISO = 12  # SPI1 MISO (GP12), typically unused by panel protocol
PIN_CS = 9     # Chip-select for the e-paper controller
PIN_DC = 8     # Data/Command select
PIN_RST = 12   # Hardware reset
PIN_BUSY = 13  # Busy line from panel (1 = busy)
BUSY_ACTIVE = 1
