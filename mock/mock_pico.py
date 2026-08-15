from __future__ import annotations

import logging
import signal
import sys
from http.server import HTTPServer

from requests import Session

from common_config import CONFIG as UNIFIED_CONFIG
from mock.handler import create_handler

CONFIG = UNIFIED_CONFIG.mock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)

HTTP_SESSION = Session()
_SERVER: HTTPServer | None = None

# Backwards-compatible name: code may import `Handler` from this module
Handler = create_handler(config=CONFIG, logger=LOGGER)


def _shutdown_server(*_args) -> None:
    # `global` without an assignment does nothing — _SERVER is only read here.
    LOGGER.info("Shutting down dashboard server")
    try:
        if _SERVER is not None:
            _SERVER.shutdown()
            _SERVER.server_close()
    finally:
        HTTP_SESSION.close()
    sys.exit(0)


def run_server() -> None:
    global _SERVER
    server_address = ("127.0.0.1", int(CONFIG.port))
    LOGGER.info("Dashboard server listening on http://%s:%s", *server_address)
    _SERVER = HTTPServer(server_address, Handler)
    _SERVER.serve_forever()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _shutdown_server)
    signal.signal(signal.SIGTERM, _shutdown_server)
    run_server()
