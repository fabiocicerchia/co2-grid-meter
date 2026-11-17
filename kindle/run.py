"""Run the Pico firmware's fetch-and-render loop on a jailbroken Kindle.

The same pico/ modules, unchanged, under the Kindle's CPython 3.9: shims/
stands in for the MicroPython-only modules, and shims/epd_driver.py draws to
the Kindle's screen instead of the Waveshare panel. No HTTP server: the Kindle
is the display, not an API.

    python3 run.py            # a render every render_min_interval_sec, until
                              # any key on the Kindle is pressed
    python3 run.py --once     # until the first real render, then exit; 1 if
                              # none within 2 minutes (CO2_EIPS= for PNG only)

settings.json is read from the current directory, as on the Pico.
"""

import contextlib
import gc
import glob

# Before pico/ goes on the path: pico/http.py would otherwise shadow the stdlib
# package that urllib needs. Once these are in sys.modules, it cannot.
import http.client  # noqa: F401
import os
import select
import socket
import struct
import sys
import time
import urllib.request  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
# Built layout (kindle/build.sh) puts the firmware in app/; in the repo it is
# ../pico.
APP = os.path.join(HERE, "app") if os.path.isdir(os.path.join(HERE, "app")) else os.path.join(HERE, "..", "pico")
sys.path[:0] = [os.path.join(HERE, "shims"), APP]

NTP_EPOCH_OFFSET_SEC = 2208988800
_real_time = time.time
_skew = 0.0


def ntp_skew(host="pool.ntp.org"):
    """Seconds to add to the Kindle's clock to get true UTC.

    A retired Kindle no longer gets its time from Amazon, and its clock may be
    days out. Measured rather than set: setting it needs root, and drift is
    corrected again on the next sync.
    """
    query = bytearray(48)
    query[0] = 0x1B
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(5)
        sock.sendto(query, socket.getaddrinfo(host, 123)[0][-1])
        reply = sock.recv(48)
    finally:
        sock.close()
    return struct.unpack("!I", reply[40:44])[0] - NTP_EPOCH_OFFSET_SEC - _real_time()


def install_device_clock(offset_for):
    """Make `time` behave as on the Pico: time.time() reads local wall-clock
    seconds and localtime() is gmtime(). pico/ is written against that (see
    utils.utc_offset_now), so the provider windows and the clock on screen are
    only right if the Kindle keeps the same convention.

    Both tuple functions are replaced rather than TZ set: the Kindle's Python
    is built without time.tzset().
    """
    real_gmtime = time.gmtime

    def device_time():
        utc = _real_time() + _skew
        return utc + offset_for(real_gmtime(int(utc)))

    def device_tuple(secs=None):
        # With no argument these read the C clock, not time.time(); on the Pico
        # both come from the RTC, so both follow the device clock here too.
        return real_gmtime(device_time() if secs is None else secs)

    time.time = device_time
    time.gmtime = device_tuple
    time.localtime = device_tuple


def open_keys():
    """The Kindle's input devices, drained of anything already queued.

    With the framework stopped (bin/start.sh), nothing else reads the keys, so
    a press is the way out. Whatever is queued already — the release of the
    press that launched this from KUAL — is read off and dropped first. On a
    desktop the devices are root-only and the list is empty.
    """
    fds = []
    for path in glob.glob("/dev/input/event*"):
        try:
            fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            continue
    key_pressed(fds, 0)
    return fds


def key_pressed(fds, timeout):
    """Wait up to `timeout` seconds; True if any key went down or up meanwhile."""
    if not fds:
        time.sleep(timeout)
        return False
    ready = select.select(fds, [], [], timeout)[0]
    for fd in ready:
        with contextlib.suppress(OSError):
            os.read(fd, 4096)
    return bool(ready)


def main(argv):
    global _skew
    once = "--once" in argv

    # MicroPython-only; utils.free_mem() logs it.
    gc.mem_free = lambda: 0

    from timeutil import utc_offset_seconds

    from config import CONFIG

    def offset_for(utc_tuple):
        return utc_offset_seconds(
            utc_tuple,
            standard_hours=CONFIG.defaults.utc_offset_hours,
            observes_dst=CONFIG.defaults.observes_eu_dst,
        )

    try:
        _skew = ntp_skew()
    except OSError as error:
        print("NTP failed, trusting the Kindle clock: %s" % error)
    install_device_clock(offset_for)

    import fw_graph
    import fw_network
    import fw_render

    # The cap exists for the Pico's portrait layout; here the graph fills
    # whatever the screen has below the panel.
    fw_graph.GRAPH_MAX_HEIGHT = 10_000

    fw_network.wifi_connect()
    keys = [] if once else open_keys()
    next_sync = time.time() + 6 * 3600
    give_up = time.time() + 120
    while True:
        fw_render._display_tick()
        if once and fw_render._last_render:
            return 0
        if once and time.time() > give_up:
            return 1
        if once:
            # Only the first fetch is in the background; let the next tick in.
            fw_render._last_display_tick = 0
        if key_pressed(keys, 5):
            print("Key pressed, stopping")
            return 0
        if time.time() >= next_sync:
            next_sync = time.time() + 6 * 3600
            with contextlib.suppress(OSError):
                _skew = ntp_skew()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
