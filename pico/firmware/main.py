"""Firmware entrypoint: connect Wi-Fi then serve emissions endpoints."""

import network
import time

import fw_config
from fw_http import serve_forever

try:
    import urequests as requests
except Exception:
    requests = None

_wlan = None


def wifi_connect(timeout_ms=15000):
    global _wlan

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        return True

    _wlan.connect(fw_config.CONFIG.wifi.ssid, fw_config.CONFIG.wifi.password)
    start_ticks = time.ticks_ms()
    while not _wlan.isconnected():
        time.sleep_ms(200)
        if time.ticks_diff(time.ticks_ms(), start_ticks) > timeout_ms:
            return False
    return True


def wifi_ok():
    return bool(_wlan) and _wlan.isconnected()


def main():
    connected = wifi_connect()
    print("WiFi:", "connected" if connected else "not connected")
    if not requests:
        print("WARNING: urequests not available; provider calls will fail.")
    serve_forever(wifi_ok)


main()
