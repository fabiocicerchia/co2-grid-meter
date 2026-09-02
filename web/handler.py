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


def create_handler(
    *, config: Any, logger: Any, http_session: Session
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler class bound to the given dependencies."""

    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"

    def _pico_base_url(query: dict[str, list[str]]) -> str:
        if "pico" in query:
            return query["pico"][0]
        return config.upstream.pico_base_url

    def _return_error_payload(error: str, details: str):
        payload = {"error": error, "details": details}
        return json.dumps(payload), 502

    def _request_with_retry(url: str, params: dict):
        last_error: Exception | None = None
        for attempt in range(config.upstream.max_retries):
            try:
                return http_session.get(
                    url,
                    params=params,
                    timeout=config.upstream.request_timeout_seconds,
                )
            except RequestException as error:
                last_error = error
                if attempt == config.upstream.max_retries - 1:
                    break
                backoff_seconds = 0.5 * (2**attempt)
                logger.warning(
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
        query: dict[str, list[str]], path: str, extra_params: dict | None = None
    ):
        base_url = _pico_base_url(query)
        target_url = f"{base_url}{path}"
        query_params = {**(extra_params or {})}

        try:
            response = _request_with_retry(target_url, query_params)
            if not response.ok:
                return _return_error_payload(
                    f"Pico returned HTTP {response.status_code}",
                    response.text[:800] if response.text else "",
                )
            return response.json(), 200

        except RequestException as error:
            return _return_error_payload("Failed to reach Pico", str(error))

        except ValueError as error:
            return _return_error_payload("Pico returned non-JSON response", str(error))

    def _pico_get_text(
        query: dict[str, list[str]], path: str, extra_params: dict | None = None
    ):
        """Like _pico_get_json, but relays the body untouched.

        An error still comes back as the JSON error payload — a dashboard that
        answered a failed CSV fetch with a valid-looking empty CSV would teach
        the consumer that the grid went quiet.
        """
        base_url = _pico_base_url(query)
        try:
            response = _request_with_retry(
                f"{base_url}{path}", {**(extra_params or {})}
            )
            if not response.ok:
                return _return_error_payload(
                    f"Pico returned HTTP {response.status_code}",
                    response.text[:800] if response.text else "",
                )
            return response.text, 200
        except RequestException as error:
            return _return_error_payload("Failed to reach Pico", str(error))

    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        """Serves static dashboard assets and proxies API calls to Pico."""

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)

            content_type = "text/plain"
            status_code = 404
            body: Any = ""

            if url.path == "/":
                status_code = 200
                content_type = "text/html"
                body = _read_text(static_dir / "index.html")
            elif url.path == "/static/style.css":
                status_code = 200
                content_type = "text/css"
                body = _read_text(static_dir / "style.css")
            elif url.path == "/static/script.js":
                status_code = 200
                content_type = "application/javascript"
                body = _read_text(static_dir / "script.js")
            elif url.path in ("/html/graph", "/html/graph.html"):
                status_code = 200
                content_type = "text/html"
                body = _read_text(static_dir / "graph.html")
            elif url.path == "/api/status":
                content_type = "application/json"
                body, status_code = _pico_get_json(query, "/status")
            elif url.path == "/api/em/window":
                content_type = "application/json"
                extra_params: dict[str, Any] = {}
                if "back_hours" in query:
                    extra_params["back_hours"] = int(query["back_hours"][0])
                body, status_code = _pico_get_json(
                    query, "/em/window", extra_params=extra_params
                )
            elif url.path == "/api/em/window.csv":
                # Proxied verbatim: the point of the CSV is that it is the same
                # bytes the device serves, so a Home Assistant sensor pointed at
                # the dashboard and one pointed at the Pico agree.
                content_type = "text/csv"
                extra_params: dict[str, Any] = {}
                if "back_hours" in query:
                    extra_params["back_hours"] = int(query["back_hours"][0])
                body, status_code = _pico_get_text(
                    query, "/em/window.csv", extra_params=extra_params
                )
            elif url.path == "/api/em/summary":
                content_type = "application/json"
                body, status_code = _pico_get_json(query, "/em/summary")
            elif url.path == "/api/em/window-overlay":
                content_type = "application/json"
                extra_params: dict[str, Any] = {}
                if "back_hours" in query:
                    extra_params["back_hours"] = int(query["back_hours"][0])
                if "forward_hours" in query:
                    extra_params["forward_hours"] = int(query["forward_hours"][0])
                body, status_code = _pico_get_json(
                    query, "/em/window-overlay", extra_params=extra_params
                )

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

    return Handler
