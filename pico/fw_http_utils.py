"""HTTP parsing/response helpers shared with firmware."""

from __future__ import annotations


def readline(conn):
    line = b""
    while True:
        char = conn.recv(1)
        if not char:
            break
        line += char
        if line.endswith(b"\r\n"):
            break
        if len(line) > 2048:
            break
    return line


def parse_request(conn):
    first_line = readline(conn).decode().strip()
    if not first_line:
        return None

    parts = first_line.split()
    if len(parts) < 2:
        return None

    method, path_with_query = parts[0], parts[1]
    while True:
        header_line = readline(conn)
        if not header_line or header_line == b"\r\n":
            break
    return method, path_with_query


def split_path_qs(path_qs: str):
    if "?" not in path_qs:
        return path_qs, {}

    path, query_string = path_qs.split("?", 1)
    params = {}
    for pair in query_string.split("&"):
        if not pair:
            continue
        if "=" in pair:
            key, value = pair.split("=", 1)
        else:
            key, value = pair, ""
        params[key] = value
    return path, params


def send_json(conn, code: int, payload):
    try:
        import ujson as json  # type: ignore
    except Exception:  # pragma: no cover
        import json  # type: ignore

    body = json.dumps(payload)
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n"
        "\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())
