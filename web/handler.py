"""HTTP handler for the dashboard proxy server.

This module is intentionally init-light: it does not configure logging, load
configuration, or create long-lived network objects. The server entrypoint
(`web/server.py`) wires those dependencies and builds the handler via
`create_handler`.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from requests import Session
from requests.exceptions import RequestException

STATIC_DIR = Path(__file__).resolve().parent / "static"

# URL path -> the file under STATIC_DIR and the type it is served as.
STATIC_ROUTES = {
    "/": ("text/html", "index.html"),
    "/static/style.css": ("text/css", "style.css"),
    "/static/script.js": ("application/javascript", "script.js"),
    "/html/graph": ("text/html", "graph.html"),
    "/html/graph.html": ("text/html", "graph.html"),
}

# URL path -> the Pico path it proxies to, and the query parameters forwarded
# with it. Anything not listed here is dropped rather than passed upstream.
API_ROUTES = {
    "/api/status": ("/status", ()),
    "/api/em/window": ("/em/window", ("back_hours",)),
    "/api/em/window-overlay": ("/em/window-overlay", ("back_hours", "forward_hours")),
    "/api/em/summary": ("/em/summary", ()),
}

# The one route relayed as text rather than JSON. Same shape as API_ROUTES; kept
# apart because the point of the CSV is that these are the device's own bytes —
# a Home Assistant sensor pointed at the dashboard and one pointed at the Pico
# have to agree, and re-serialising through JSON would break that.
TEXT_ROUTES = {
    "/api/em/window.csv": ("/em/window.csv", ("back_hours",), "text/csv"),
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class PicoProxyHandler(BaseHTTPRequestHandler):
    """Serves static dashboard assets and proxies API calls to Pico.

    The dependencies are class attributes rather than `__init__` arguments:
    `HTTPServer` constructs a handler per request and controls that signature,
    so `create_handler` binds them onto a subclass instead.
    """

    config: Any = None
    logger: Any = None
    http_session: Session | None = None

    def _pico_base_url(self, query: dict[str, list[str]]) -> str:
        if "pico" in query:
            return query["pico"][0]
        return self.config.upstream.pico_base_url

    @staticmethod
    def _return_error_payload(error: str, details: str):
        payload = {"error": error, "details": details}
        return json.dumps(payload), 502

    def _request_with_retry(self, url: str, params: dict):
        last_error: Exception | None = None
        for attempt in range(self.config.upstream.max_retries):
            try:
                return self.http_session.get(
                    url,
                    params=params,
                    timeout=self.config.upstream.request_timeout_seconds,
                )
            except RequestException as error:
                last_error = error
                if attempt == self.config.upstream.max_retries - 1:
                    break
                backoff_seconds = 0.5 * (2**attempt)
                self.logger.warning(
                    "Pico request failed, retrying",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "backoff": backoff_seconds,
                        "error": error,
                    },
                )
                time.sleep(backoff_seconds)
        assert last_error is not None
        raise last_error

    def _pico_get_json(
        self,
        query: dict[str, list[str]],
        path: str,
        extra_params: dict | None = None,
    ):
        base_url = self._pico_base_url(query)
        target_url = f"{base_url}{path}"
        query_params = {**(extra_params or {})}

        try:
            response = self._request_with_retry(target_url, query_params)
            if not response.ok:
                return self._return_error_payload(
                    f"Pico returned HTTP {response.status_code}",
                    response.text[:800] if response.text else "",
                )
            return response.json(), 200

        except RequestException as error:
            return self._return_error_payload("Failed to reach Pico", str(error))

        except ValueError as error:
            return self._return_error_payload(
                "Pico returned non-JSON response", str(error)
            )

    def _pico_get_text(
        self, query: dict[str, list[str]], path: str, extra_params: dict | None = None
    ):
        """Like _pico_get_json, but relays the body untouched.

        An error still comes back as the JSON error payload — a dashboard that
        answered a failed CSV fetch with a valid-looking empty CSV would teach
        the consumer that the grid went quiet.
        """
        base_url = self._pico_base_url(query)
        try:
            response = self._request_with_retry(
                f"{base_url}{path}", {**(extra_params or {})}
            )
            if not response.ok:
                return self._return_error_payload(
                    f"Pico returned HTTP {response.status_code}",
                    response.text[:800] if response.text else "",
                )
            return response.text, 200
        except RequestException as error:
            return self._return_error_payload("Failed to reach Pico", str(error))

    def _respond_to(self, path: str, query: dict[str, list[str]]):
        """(content_type, body, status) for one URL path.

        Two tables rather than a chain of seven elifs: a static route differs
        only in its file and type, and a proxied one only in the Pico path and
        the parameters it forwards.
        """
        if path in STATIC_ROUTES:
            content_type, filename = STATIC_ROUTES[path]
            return content_type, _read_text(STATIC_DIR / filename), 200

        export = TEXT_ROUTES.get(path)
        if export is not None:
            pico_path, forwarded, content_type = export
            extra_params: dict[str, Any] = {
                name: int(query[name][0]) for name in forwarded if name in query
            }
            body, status_code = self._pico_get_text(
                query, pico_path, extra_params=extra_params
            )
            return content_type, body, status_code

        route = API_ROUTES.get(path)
        if route is None:
            return "text/plain", "", 404

        pico_path, forwarded = route
        extra_params = {
            name: int(query[name][0]) for name in forwarded if name in query
        }
        body, status_code = self._pico_get_json(
            query, pico_path, extra_params=extra_params
        )
        return "application/json", body, status_code

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        content_type, body, status_code = self._respond_to(url.path, query)

        self.protocol_version = "HTTP/1.1"
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.end_headers()

        body_bytes = (
            json.dumps(body).encode("utf-8")
            if isinstance(body, (dict, list))
            else str(body).encode("utf-8")
        )
        self.wfile.write(body_bytes)


def create_handler(
    *, config: Any, logger: Any, http_session: Session
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class bound to the given dependencies."""
    return type(
        "Handler",
        (PicoProxyHandler,),
        {"config": config, "logger": logger, "http_session": http_session},
    )
