import json
import threading
from http.server import HTTPServer
from urllib.request import urlopen

from pico.models import GeoLocation

from mock import handler as mock_handler


class _FakeResolver:
    def __init__(self, *_args, **_kwargs):
        pass

    def resolve(self, _request):
        return GeoLocation(41.9, 12.5, "IT", "Rome", "test")


class _FakeWindowService:
    def __init__(self):
        self.calls = 0

    def fetch_window(self, *_args, **_kwargs):
        self.calls += 1
        return {
            "history": [{"datetime": "2024-01-01T00:00:00Z", "carbonIntensity": 120}],
            "provider": "fake",
        }


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _get_json(url):
    with urlopen(url) as response:  # noqa: S310 - local test server
        return response.status, json.loads(response.read().decode("utf-8"))


def test_mock_pico_endpoints_return_200_and_cache(monkeypatch):
    fake_service = _FakeWindowService()
    monkeypatch.setattr(mock_handler, "GeoResolver", _FakeResolver)
    monkeypatch.setattr(mock_handler, "_make_window_service", lambda *_args, **_kwargs: fake_service)

    class _Config:
        cache_refresh_seconds = 3600

    handler_cls = mock_handler.create_handler(config=_Config(), logger=type("L", (), {"exception": lambda *a, **k: None})(), http_session=object())
    server, base_url = _serve(handler_cls)

    try:
        assert _get_json(f"{base_url}/em/window?back_hours=2")[0] == 200
        assert _get_json(f"{base_url}/em/window-overlay")[0] == 200
        status_code, payload = _get_json(f"{base_url}/status")
        assert status_code == 200
        assert payload["city"] == "Rome"
        # status and overlay each call fetch_window once; repeated status should be cached.
        assert _get_json(f"{base_url}/status")[0] == 200
        assert fake_service.calls == 4
    finally:
        server.shutdown()
        server.server_close()
