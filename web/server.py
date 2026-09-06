"""Dashboard proxy server entrypoint.

This file contains init & wiring (config, logging, HTTP session, server lifecycle).
The request handling logic lives in `web/handler.py`.
"""

from __future__ import annotations

import logging
import signal
import sys
from http.server import HTTPServer

from requests import Session

from common_config import CONFIG as UNIFIED_CONFIG
from web.handler import create_handler

CONFIG = UNIFIED_CONFIG.web

logging.basicConfig(
    level=CONFIG.logging.level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("web.server")

HTTP_SESSION = Session()

# Backwards-compatible name: code may import `Handler` from this module
Handler = create_handler(config=CONFIG, logger=LOGGER, http_session=HTTP_SESSION)


def _shutdown(server: HTTPServer) -> None:
    """Stop serving and close the upstream session, then exit."""
    LOGGER.info("Shutting down dashboard server")
    try:
        server.shutdown()
        server.server_close()
    finally:
        HTTP_SESSION.close()
    sys.exit(0)


def run_server() -> None:
    """Serve until a signal arrives.

    The signal handlers are registered here, closing over the server, rather
    than reaching for a module-level one: the handler cannot fire before there
    is something to shut down, and nothing else in the module can see it.
    """
    server_address = ("127.0.0.1", CONFIG.server.port)
    LOGGER.info("Dashboard server listening on http://%s:%s", *server_address)
    server = HTTPServer(server_address, Handler)
    for received in (signal.SIGINT, signal.SIGTERM):
        signal.signal(received, lambda *_args: _shutdown(server))
    server.serve_forever()


if __name__ == "__main__":
    run_server()
