"""Boot and WiFi reconnect put the same local time in the RTC.

The reconnect path used to call `set_time(2)` — a fixed offset, and two
*seconds* at that, where the boot path derives the offset from
`CONFIG.defaults` plus EU summer time. A device that reconnected ran on the
wrong clock until it rebooted.

`pico/http.py` imports MicroPython-only modules, so it is loaded by path with
those modules stubbed in `sys.modules` for the duration of the load. NTP is a
fake socket that answers with a chosen instant; the RTC is a fake that records
what it was set to. Nothing here touches the network.
"""

import ast
import importlib.util
import pathlib
import struct
import sys
import types
from unittest import mock

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"
NTP_EPOCH_OFFSET_SEC = 2208988800

# 12:00 UTC on a January day and on a July day: Italy is UTC+1 and UTC+2.
WINTER = (1768478400, 13)  # 2026-01-15 12:00 UTC -> 13:00 local
SUMMER = (1782907200, 14)  # 2026-07-01 12:00 UTC -> 14:00 local


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeRTC:
    def __init__(self, sink):
        self._sink = sink

    def datetime(self, value):
        self._sink.append(value)


def _ntp_socket(unix_epoch):
    reply = bytearray(48)
    reply[40:44] = struct.pack("!I", unix_epoch + NTP_EPOCH_OFFSET_SEC)

    class _Sock:
        def settimeout(self, _seconds):
            pass

        def sendto(self, _data, _addr):
            pass

        def recv(self, _n):
            return bytes(reply)

        def close(self):
            pass

    return types.SimpleNamespace(
        AF_INET=2,
        SOCK_DGRAM=2,
        getaddrinfo=lambda host, port: [(None, None, None, None, (host, port))],
        socket=lambda *_args: _Sock(),
    )


@pytest.fixture
def http_module():
    rtc_writes = []
    config = types.SimpleNamespace(
        CONFIG=types.SimpleNamespace(
            defaults=types.SimpleNamespace(
                utc_offset_hours=1,
                observes_eu_dst=True,
                city="Rome",
                country="IT",
            ),
        ),
        append_log_line=mock.MagicMock(),
        write_crashdump=mock.MagicMock(),
    )
    machine = types.SimpleNamespace(RTC=lambda: _FakeRTC(rtc_writes))
    stubs = {
        name: mock.MagicMock()
        for name in (
            "network",
            "staticfiles",
            "ujson",
            "uos",
            "app",
            "display",
            "fw_network",
            "fw_render",
            "pages",
            "utils",
        )
    }
    stubs["machine"] = machine
    stubs["config"] = config
    stubs["timeutil"] = _load(PICO / "timeutil.py", "timeutil")
    with mock.patch.dict(sys.modules, stubs):
        # Not as `http`: that would shadow the standard library's package.
        module = _load(PICO / "http.py", "pico_http_under_test")
    module.rtc_writes = rtc_writes
    return module


def _boot(module, unix_epoch):
    module.socket = _ntp_socket(unix_epoch)
    module.set_time()  # what main.py calls at boot
    return module.rtc_writes.pop()


def _reconnect(module, unix_epoch):
    module.socket = _ntp_socket(unix_epoch)
    module.wifi_ok = lambda: False
    module.wifi_connect = lambda: (True, "192.0.2.10")
    module.open_socket = lambda _ip: None
    assert module.ensure_connected("192.0.2.9") == "192.0.2.10"
    return module.rtc_writes.pop()


@pytest.mark.parametrize(("instant", "local_hour"), [WINTER, SUMMER], ids=["winter", "summer"])
def test_reconnect_sets_the_same_local_time_as_boot(http_module, instant, local_hour):
    booted = _boot(http_module, instant)
    reconnected = _reconnect(http_module, instant)

    assert reconnected == booted
    # Field 4 of the RTC tuple is the hour.
    assert booted[4] == local_hour


@pytest.mark.parametrize("name", ["main.py", "http.py"])
def test_no_caller_passes_set_time_an_offset(name):
    # The boot path is the reference the reconnect test compares against, so
    # neither it nor anything else may hand set_time a literal offset again.
    tree = ast.parse((PICO / name).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "set_time"
    ]
    assert calls, f"expected {name} to call set_time"
    assert all(not call.args and not call.keywords for call in calls)
