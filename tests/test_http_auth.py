"""The firmware HTTP server's optional token.

Unset, every route answers as before. Set, every route — /system-info above
all, since it reports the device's IP, gateway, DNS and ISP — needs
`Authorization: Bearer <token>` and otherwise gets a 401 that does not say
which part was wrong.

`pico/http.py` imports MicroPython-only modules, so it is loaded by path with
those stubbed in `sys.modules` for the duration of the load. Not as `http`:
that would shadow the standard library's package.
"""

import importlib.util
import json
import pathlib
import sys
import types
from unittest import mock

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"
TOKEN = "s3cret-token"


class FakeConn:
    """A socket that serves `request` one byte at a time and records replies."""

    def __init__(self, request=b""):
        self._pending = request
        self.sent = b""

    def recv(self, n):
        chunk, self._pending = self._pending[:n], self._pending[n:]
        return chunk

    def send(self, data):
        self.sent += data

    def close(self):
        pass

    @property
    def status(self):
        return int(self.sent.split(b" ", 2)[1])

    @property
    def body(self):
        return self.sent.split(b"\r\n\r\n", 1)[1]


@pytest.fixture
def server():
    web = types.SimpleNamespace(serve_static=False, static_root="static", api_token="")
    config = types.SimpleNamespace(
        CONFIG=types.SimpleNamespace(web=web),
        append_log_line=mock.MagicMock(),
        write_crashdump=mock.MagicMock(return_value="crash.txt"),
    )
    app = mock.MagicMock()
    app.handle_system_info.return_value = {"ip": "192.0.2.10", "isp": "Example ISP"}
    app.handle_status.return_value = {"carbonIntensity": 210}
    app.handle_em_window_csv.return_value = "ts,ci\n"
    pages = mock.MagicMock()
    pages.MINI_HTML = "<html></html>"
    stubs = {
        name: mock.MagicMock()
        for name in (
            "machine",
            "network",
            "staticfiles",
            "uos",
            "display",
            "fw_network",
            "fw_render",
            "timeutil",
            "utils",
        )
    }
    stubs.update({"app": app, "pages": pages, "config": config, "ujson": json})
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("pico_http_auth_under_test", PICO / "http.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.web = web
    return module


def _request(server, path, authorization=""):
    conn = FakeConn()
    server.process_http_request(conn, "GET", path, {}, "", authorization)
    return conn


ROUTES = ["/system-info", "/status", "/em/window.csv", "/html/"]


@pytest.mark.parametrize("path", ROUTES)
def test_no_token_configured_leaves_every_route_open(server, path):
    assert _request(server, path).status == 200


@pytest.mark.parametrize("path", ROUTES)
def test_a_configured_token_is_required_on_every_route(server, path):
    server.web.api_token = TOKEN

    assert _request(server, path).status == 401
    assert _request(server, path, "Bearer " + TOKEN).status == 200


def test_system_info_discloses_nothing_without_the_token(server):
    server.web.api_token = TOKEN

    refused = _request(server, "/system-info")
    assert refused.status == 401
    assert b"192.0.2.10" not in refused.sent
    assert json.loads(refused.body) == {"error": "Unauthorized"}

    allowed = _request(server, "/system-info", "Bearer " + TOKEN)
    assert json.loads(allowed.body)["ip"] == "192.0.2.10"


@pytest.mark.parametrize(
    "authorization",
    [
        "",
        "Bearer wrong-token-",
        "Bearer " + TOKEN[:-1],
        "Basic " + TOKEN,
        TOKEN,
        "Bearer",
    ],
)
def test_every_wrong_credential_gets_the_same_answer(server, authorization):
    server.web.api_token = TOKEN

    conn = _request(server, "/status", authorization)

    assert conn.status == 401
    assert json.loads(conn.body) == {"error": "Unauthorized"}


def test_the_scheme_is_case_insensitive(server):
    server.web.api_token = TOKEN

    assert _request(server, "/status", "bearer " + TOKEN).status == 200


def test_whitespace_around_the_configured_token_is_ignored(server):
    server.web.api_token = " " + TOKEN + "\n"

    assert _request(server, "/status", "Bearer " + TOKEN).status == 200
    assert _request(server, "/status").status == 401


def test_a_whitespace_only_token_is_no_token(server):
    server.web.api_token = "   "

    assert _request(server, "/status").status == 200


@pytest.mark.parametrize("configured", [123456, True, 0.5])
def test_a_non_string_token_is_enforced_as_its_text(server, configured):
    server.web.api_token = configured

    assert _request(server, "/status").status == 401
    assert _request(server, "/status", f"Bearer {configured}").status == 200


def test_unknown_paths_are_refused_before_they_are_looked_up(server):
    server.web.api_token = TOKEN

    assert _request(server, "/no-such-route").status == 401


def test_parse_request_keeps_the_authorization_header(server):
    raw = (
        b"GET /system-info HTTP/1.1\r\n"
        b"Host: pico\r\n"
        b"AUTHORIZATION: Bearer " + TOKEN.encode() + b"\r\n"
        b'If-None-Match: "abc"\r\n'
        b"\r\n"
    )

    assert server.parse_request(FakeConn(raw)) == ("GET", "/system-info", '"abc"', "Bearer " + TOKEN)


def test_handle_http_request_threads_the_header_through(server):
    server.web.api_token = TOKEN
    logger = mock.MagicMock()
    raw = b"GET /status HTTP/1.1\r\nAuthorization: Bearer " + TOKEN.encode() + b"\r\n\r\n"

    with_token = FakeConn(raw)
    server.handle_http_request(with_token, logger)
    without = FakeConn(b"GET /status HTTP/1.1\r\n\r\n")
    server.handle_http_request(without, logger)

    assert (with_token.status, without.status) == (200, 401)
