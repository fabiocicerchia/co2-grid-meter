"""MicroPython's `network`, for a device whose OS already runs the Wi-Fi.

The Kindle connects on its own; pico/fw_network.py only needs to be told it is
connected and what the interface looks like, for the top-bar icon and the logs.
"""

import socket

STA_IF = 0


def _local_ip():
    # A UDP "connect" sends nothing; it only asks the kernel which address it
    # would route from.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("1.1.1.1", 53))
            return probe.getsockname()[0]
        finally:
            probe.close()
    except OSError:
        return ""


class WLAN:
    def __init__(self, _interface=STA_IF):
        pass

    def active(self, _on=None):
        return True

    def isconnected(self):
        return bool(_local_ip())

    def connect(self, *_args):
        pass

    def ifconfig(self):
        return (_local_ip(), "", "", "")

    def status(self, _what=None):
        # No RSSI from here without root tools; None draws as no bars, which
        # would read as "down". Full bars while there is a route out.
        return -50
