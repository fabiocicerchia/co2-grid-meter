"""Minimal HTTP server for Pico endpoints."""

import gc
import socket

import fw_app
import fw_config

from pico.fw_http_utils import parse_request, send_json, split_path_qs


def serve_forever(wifi_connected_callback):
    addr = socket.getaddrinfo(
        fw_config.CONFIG.server.host, fw_config.CONFIG.server.port
    )[0][-1]
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(addr)
    server_socket.listen(2)
    print(
        "Pico running: http://%s:%d"
        % (fw_config.CONFIG.server.host, fw_config.CONFIG.server.port)
    )

    while True:
        conn, _ = server_socket.accept()
        try:
            request = parse_request(conn)
            if not request:
                conn.close()
                continue

            method, path_qs = request
            path, params = split_path_qs(path_qs)

            if method != "GET":
                send_json(conn, 405, {"error": "Only GET supported"})
                continue

            if path == "/em/window":
                send_json(conn, 200, fw_app.handle_em_window(params))
            elif path == "/em/window-overlay":
                send_json(conn, 200, fw_app.handle_em_overlay(params))
            elif path == "/status":
                status = fw_app.handle_status(params, wifi_connected_callback)
                send_json(conn, 200, status)
            else:
                send_json(conn, 404, {"error": "Not found", "path": path})
        except Exception as error:
            send_json(conn, 500, {"error": "Internal error", "details": str(error)})
        finally:
            try:
                conn.close()
            except Exception:
                pass
            gc.collect()
