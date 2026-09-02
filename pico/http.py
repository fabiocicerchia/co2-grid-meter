import socket
import struct
import time

import machine
import network
import staticfiles
import ujson
import uos
from app import (
    _display_tick,
    handle_em_overlay,
    handle_em_window,
    handle_status,
    handle_system_info,
    render_placeholder_screen,
)
from display import get_epd
from fw_network import wifi_connect, wifi_ok
from pages import GRAPH_HTML, MINI_HTML, build_index_html
from timeutil import utc_offset_seconds
from utils import _now_stamp, log

from config import CONFIG, append_log_line, write_crashdump

_server_socket = None

# Seconds between the NTP epoch (1900-01-01) and the Unix epoch.
NTP_EPOCH_OFFSET_SEC = 2208988800


def _readline(conn):
    # Collected then joined once: `line += ch` rebuilt the whole bytes object
    # on every byte, which is O(n^2) over the line.
    chars = []
    while True:
        ch = conn.recv(1)
        if not ch:
            break
        chars.append(ch)
        if (chars[-2:] == [b"\r", b"\n"]) or len(chars) > 2048:
            break
    return b"".join(chars)


def parse_request(conn):
    first = _readline(conn).decode().strip()
    if not first:
        return None
    parts = first.split()
    if len(parts) < 2:
        return None
    method, path_qs = parts[0], parts[1]
    # Only If-None-Match is kept: it is the one header this server acts on, and
    # holding a whole header dict per request costs heap the device needs for
    # the response.
    if_none_match = ""
    while True:
        h = _readline(conn)
        if not h or h == b"\r\n":
            break
        # Matched as bytes: decoding every header to find the one that matters
        # allocates a string per header per request, which is the heap this
        # was trying to save. Only the value that is actually kept is decoded,
        # and a header that is not valid UTF-8 is not one this server acts on.
        if h[:14].lower() == b"if-none-match:":
            try:
                if_none_match = h[14:].decode().strip()
            except Exception:
                if_none_match = ""
    return method, path_qs, if_none_match


def split_path_qs(path_qs):
    if "?" not in path_qs:
        return path_qs, {}
    path, query = path_qs.split("?", 1)
    params = {}
    for pair in query.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
        else:
            k, v = pair, ""
        params[k] = v
    return path, params


def _send_response(conn, code, content_type, body):
    body_bytes = body.encode()
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: %s\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, content_type, len(body_bytes))
    conn.send(headers.encode())
    conn.send(body_bytes)


def send_json(conn, code, payload):
    _send_response(conn, code, "application/json", ujson.dumps(payload))


def send_html(conn, code, body):
    _send_response(conn, code, "text/html; charset=utf-8", body)


def send_text(conn, code: int, body: str, content_type: str = "text/plain"):
    _send_response(conn, code, content_type, body)


def set_time(offset=None, epoch_offset=NTP_EPOCH_OFFSET_SEC, host="pool.ntp.org"):
    """Set the RTC from NTP, in local wall-clock time.

    `offset` is seconds to add to UTC. Left as None it is derived from
    `CONFIG.defaults.utc_offset_hours` plus EU summer time, so the clock is
    right on both sides of the March and October changes instead of running an
    hour out for seven months of the year.
    """
    NTP_QUERY = bytearray(48)
    NTP_QUERY[0] = 0x1B
    addr = socket.getaddrinfo(host, 123)[0][-1]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1)
        sock.sendto(NTP_QUERY, addr)
        reply = sock.recv(48)
    finally:
        sock.close()
    ntp_seconds = struct.unpack("!I", reply[40:44])[0]
    unix_epoch = ntp_seconds - epoch_offset
    if offset is None:
        # Decided from the UTC instant, never from the already-shifted one:
        # applying the rule to local time is what makes the repeated hour
        # ambiguous.
        offset = utc_offset_seconds(
            time.gmtime(unix_epoch),
            standard_hours=CONFIG.defaults.utc_offset_hours,
            observes_dst=CONFIG.defaults.observes_eu_dst,
        )
    tm = time.gmtime(unix_epoch + offset)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    log("Local time: %s (UTC%+d)" % (_now_stamp(), offset // 3600))


def handle_http_request(conn, logger):
    if conn is None:
        return

    request = parse_request(conn)
    if not request:
        return

    method, path_qs, if_none_match = request
    path, params = split_path_qs(path_qs)
    logger.info("%s %s" % (method, path))

    try:
        process_http_request(conn, method, path, params, if_none_match)
    except Exception as error:
        crash_path = write_crashdump(error, context="http")
        logger.exception("ERROR %s %s" % (error, crash_path))
        append_log_line("ERROR %s" % crash_path)
        send_json(conn, 500, {"error": "Internal error", "details": str(error)})
    finally:
        try:
            conn.close()
        except Exception:
            pass


def process_http_request(conn, method, path, params, if_none_match=""):
    if method != "GET":
        return send_json(conn, 405, {"error": "Only GET supported"})

    # Static files first: with serving enabled the dashboard's own paths must
    # not be shadowed by the JSON routes below, and with it disabled this costs
    # one attribute read.
    if getattr(CONFIG.web, "serve_static", False) and serve_static_file(
        conn, path, if_none_match
    ):
        return

    if path == "/html":
        return send_html(conn, 200, build_index_html())
    if path == "/em/window":
        return send_json(conn, 200, handle_em_window(params))
    if path == "/em/window-overlay":
        return send_json(conn, 200, handle_em_overlay(params))
    if path == "/status":
        return send_json(conn, 200, handle_status(params))
    if path == "/system-info":
        return send_json(conn, 200, handle_system_info(params, wifi_ok))
    if path == "/html/":
        return send_text(conn, 200, MINI_HTML, "text/html")
    if path == "/html/graph":
        return send_text(conn, 200, GRAPH_HTML, "text/html")

    return send_json(conn, 404, {"error": "Not found", "path": path})


def serve_static_file(conn, path, if_none_match=""):
    """Serve `path` from the static root. False means "not mine" — the caller
    then tries the JSON routes, so enabling this cannot break the API.

    Streamed in chunks: a 15 KB script read whole would be a memory failure on
    a device with tens of KB of heap, and would hold the refresh loop for the
    duration of the read.
    """
    target = staticfiles.resolve(CONFIG.web.static_root, path)
    if target is None:
        return False
    try:
        stat = uos.stat(target)
    except OSError:
        return False

    tag = staticfiles.etag(stat[6], stat[8])
    if staticfiles.not_modified(if_none_match, tag):
        # A reload of an unchanged asset is a header exchange, not a transfer:
        # the radio is the most expensive thing on the board.
        conn.send(
            (
                "HTTP/1.1 304 Not Modified\r\nETag: %s\r\nConnection: close\r\n\r\n"
                % tag
            ).encode()
        )
        return True

    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "ETag: %s\r\n"
        "Cache-Control: max-age=300\r\n"
        "Connection: close\r\n\r\n"
    ) % (staticfiles.content_type(target), stat[6], tag)
    conn.send(headers.encode())
    with open(target, "rb") as fh:
        for block in staticfiles.chunks(fh):
            conn.send(block)
    return True


def ensure_connected(ip):
    if wifi_ok():
        return ip

    log("WiFi disconnected, reconnecting...")
    close_server_socket()
    connected, new_ip = wifi_connect()
    if connected:
        try:
            ip = network.WLAN(network.STA_IF).ifconfig()[0]
            print(
                "System info: ip=%s provider=unknown location=%s,%s"
                % (ip, CONFIG.defaults.city, CONFIG.defaults.country)
            )
        except Exception:
            pass
    else:
        raise OSError("WiFi reconnect failed")

    try:
        set_time(2)  # ITALY GMT+1 # TODO: FIX DAYLIGHT
    except Exception as error:
        log("set_time after reconnect failed: %s" % error)

    open_socket(new_ip)
    return new_ip


def get_connection(logger):
    if _server_socket is None:
        return None
    try:
        conn, _ = _server_socket.accept()
        return conn
    except OSError as error:
        logger.exception("OSError %s" % error)
        return None


def close_server_socket():
    global _server_socket
    if _server_socket is None:
        return
    try:
        _server_socket.close()
    except Exception:
        pass
    _server_socket = None


def open_socket(ip):
    global _server_socket

    close_server_socket()

    addr = socket.getaddrinfo(CONFIG.server.host, CONFIG.server.port)[0][-1]
    _server_socket = socket.socket()
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(addr)
    _server_socket.listen(2)
    _server_socket.settimeout(1)
    log("Pico running: http://%s:%d" % (ip, CONFIG.server.port))


def serve_forever(ip, logger):
    global _epd

    open_socket(ip)
    _epd = get_epd()

    render_placeholder_screen("BOOT", "Waiting for data...")
    while True:
        try:
            ip = ensure_connected(ip)
            _display_tick()

            conn = get_connection(logger)
            handle_http_request(conn, logger)
        except Exception as error:
            log("serve_forever loop error: %s" % error)
            close_server_socket()
            time.sleep(1)
