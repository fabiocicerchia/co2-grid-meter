import time

import network
from utils import log

from config import CONFIG
from diagnostics import network_summary

_wlan = None


def wifi_connect(timeout_ms=15000):
    global _wlan

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)

    if _wlan.isconnected():
        ip = _log_interface()
        return True, ip

    _wlan.connect(CONFIG.wifi.ssid, CONFIG.wifi.password)
    start = time.ticks_ms()
    while not _wlan.isconnected():
        time.sleep_ms(200)
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            log("WiFi: not connected")
            return False, ""

    ip = _log_interface()
    return True, ip


def _log_interface():
    """Log the whole interface, not just the address.

    A device that gets an IP but no gateway, or a DNS server it cannot reach,
    looks identical to a healthy one when only the address is printed — and
    both fail later as a provider timeout, which is where the time goes.
    """
    net = network_summary(_wlan.ifconfig())
    log(
        "WiFi: connected %s netmask %s gateway %s dns %s"
        % (
            net["ip"] or "?",
            net["netmask"] or "?",
            net["gateway"] or "?",
            net["dns"] or "?",
        )
    )
    return net["ip"]


def interface_summary():
    """The same dict for the status endpoint, or empty when down."""
    if not wifi_ok():
        return network_summary(())
    return network_summary(_wlan.ifconfig())


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
