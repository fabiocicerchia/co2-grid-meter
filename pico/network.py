
import time
import network

from pico.config import CONFIG
from pico.utils import log

_wlan = None

def wifi_connect(timeout_ms=15000):
    global _wlan

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)

    if _wlan.isconnected():
        ip = _wlan.ifconfig()[0]
        log("WiFi: connected %s" % ip)
        return True, ip

    _wlan.connect(CONFIG.wifi.ssid, CONFIG.wifi.password)
    start = time.ticks_ms()
    while not _wlan.isconnected():
        time.sleep_ms(200)
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            log("WiFi: not connected")
            return False, ""

    ip = _wlan.ifconfig()[0]
    log("WiFi: connected %s" % ip)
    return True, ip


def wifi_ok():
    return bool(_wlan) and _wlan.isconnected()


def wifi_signal_bars():
    if not wifi_ok():
        return 0

    try:
        rssi = _wlan.status("rssi")
    except Exception:
        return 4

    if rssi is None:
        return 0

    # Typical RSSI (dBm) thresholds for 4 bars.
    if rssi >= -55:
        return 4
    if rssi >= -67:
        return 3
    if rssi >= -75:
        return 2
    if rssi >= -85:
        return 1

    return 0