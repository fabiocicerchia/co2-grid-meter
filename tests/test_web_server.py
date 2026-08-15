import json
import threading
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from web import handler as web_handler


class FakeResponse:
    def __init__(self, payload, ok=True, status_code=200, text=""):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _fetch(url):
    try:
        with urlopen(url) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _config():
    return type(
        "Config",
        (),
        {
            "upstream": type(
                "Upstream",
                (),
                {
                    "pico_base_url": "http://example.test",
                    "request_timeout_seconds": 1,
                    "max_retries": 1,
                },
            )()
        },
    )()


def test_api_status_success():
    session = FakeSession(FakeResponse({"carbonIntensity": 120}))
    handler_cls = web_handler.create_handler(
        config=_config(),
        logger=type("L", (), {"warning": lambda *a, **k: None})(),
        http_session=session,
    )
    server, base_url = _serve(handler_cls)
    try:
        status_code, payload = _fetch(f"{base_url}/api/status")
        assert status_code == 200
        assert payload["carbonIntensity"] == 120
    finally:
        server.shutdown()
        server.server_close()


def test_api_status_handles_provider_http_error():
    session = FakeSession(
        FakeResponse({"error": "bad"}, ok=False, status_code=500, text="boom")
    )
    handler_cls = web_handler.create_handler(
        config=_config(),
        logger=type("L", (), {"warning": lambda *a, **k: None})(),
        http_session=session,
    )
    server, base_url = _serve(handler_cls)
    try:
        status_code, payload = _fetch(f"{base_url}/api/status")
        assert status_code == 502
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()
