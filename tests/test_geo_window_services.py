from datetime import datetime, timedelta, timezone

from pico.config import CONFIG
from pico.geo_resolver import GeoResolver
from pico.models import GeoLocation
from pico.window_service import WindowService


class DummySession:
    def get(self, *_args, **_kwargs):
        raise RuntimeError("network disabled")


class DummyProvider:
    provider_name = "dummy"

    def __init__(self):
        self.calls = 0

    def is_enabled(self, _country_code):
        return True

    def fetch_history(self, *_args, **_kwargs):
        self.calls += 1
        return {
            "history": [{"datetime": "2024-01-01T00:00:00Z", "carbonIntensity": 123}],
            "provider": "dummy",
        }


def test_geo_resolver_uses_query_override():
    class Request:
        path = "/?lat=1.0&lon=2.0&country=it&city=rome"
        client_address = ("127.0.0.1", 1234)

    resolver = GeoResolver(CONFIG, DummySession())
    location = resolver.resolve(Request())
    assert location == GeoLocation(1.0, 2.0, "IT", "rome", "override")
