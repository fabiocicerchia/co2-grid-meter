
import struct

import machine
import socket
import time

import ujson

from pico.firmware.fw_app import _display_tick, handle_em_overlay, handle_em_window, handle_status, render_placeholder_screen
from pico.firmware.fw_config import append_log_line, write_crashdump
from pico.firmware.fw_display import get_epd
from pico.firmware.fw_utils import _now_stamp, log
from pico.firmware_fw_config import CONFIG


def _readline(conn):
    line = b""
    while True:
        ch = conn.recv(1)
        if not ch:
            break
        line += ch
        if line.endswith(b"\r\n") or len(line) > 2048:
            break
    return line


def parse_request(conn):
    first = _readline(conn).decode().strip()
    if not first:
        return None
    parts = first.split()
    if len(parts) < 2:
        return None
    method, path_qs = parts[0], parts[1]
    while True:
        h = _readline(conn)
        if not h or h == b"\r\n":
            break
    return method, path_qs


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


def send_json(conn, code, payload):
    body = ujson.dumps(payload)
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())



def send_html(conn, code, body):
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())


def build_index_html():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pico CO₂ Status</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f3f4f6; color: #111827; }
    .page { max-width: 740px; margin: 0 auto; padding: 18px; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.08); padding: 14px; margin-bottom: 12px; }
    h1 { margin: 0 0 8px 0; font-size: 22px; }
    .muted { color: #6b7280; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; }
    .k { font-size: 12px; color: #6b7280; }
    .v { font-weight: 600; margin-top: 2px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
    button { border: none; border-radius: 8px; padding: 8px 12px; background: #2563eb; color: #fff; cursor: pointer; font-weight: 600; }
    .themeBtn { background: #4b5563; }
    .pill { display: inline-block; border-radius: 999px; background: #e5e7eb; padding: 2px 8px; font-size: 12px; font-weight: 600; color: #111827; }
    .ok { background: #d1fae5; color: #065f46; }
    .wait { background: #fef3c7; color: #92400e; }
    .no { background: #fee2e2; color: #991b1b; }
    body.dark { background: #111827; color: #f9fafb; }
    body.dark .card { background: #1f2937; border-color: #374151; }
    body.dark .muted, body.dark .k { color: #9ca3af; }
    body.dark .pill { background: #374151; color: #f9fafb; }
    @media (prefers-color-scheme: dark) {
      body.auto { background: #111827; color: #f9fafb; }
      body.auto .card { background: #1f2937; border-color: #374151; }
      body.auto .muted, body.auto .k { color: #9ca3af; }
      body.auto .pill { background: #374151; color: #f9fafb; }
    }
  </style>
</head>
<body class="auto">
  <main class="page">
    <section class="card">
      <h1><span id="city">--</span> grid CO₂ status</h1>
      <div class="muted" id="meta">Waiting for /status...</div>
      <div class="row">
        <button id="refresh">Refresh</button>
        <button id="theme" class="themeBtn">Dark mode</button>
        <span class="muted">Auto refresh every 30s</span>
      </div>
    </section>
    <section class="card">
      <div class="grid">
        <div><div class="k">Carbon intensity</div><div class="v"><span id="ci">--</span> gCO₂/kWh</div></div>
        <div><div class="k">Provider</div><div class="v" id="provider">--</div></div>
        <div><div class="k">Recommendation</div><div class="v"><span class="pill" id="verdict">--</span></div></div>
        <div><div class="k">Reason</div><div class="v" id="reason">--</div></div>
        <div><div class="k">Wait hours</div><div class="v" id="wait">--</div></div>
        <div><div class="k">Next best</div><div class="v" id="next">--</div></div>
      </div>
    </section>
  </main>
  <script>
    const els = { city:city, meta:meta, ci:ci, provider:provider, verdict:verdict, reason:reason, wait:wait, next:next, refresh:refresh, theme:theme };
    function verdictClass(v){ if(v==='GO')return 'pill ok'; if(v==='WAIT')return 'pill no'; return 'pill wait'; }
    function fill(data){ const rec=data.recommendation||{}; els.city.textContent=data.city||'--'; els.meta.textContent=`${data.cc||'--'} • ${data.datetime||'--'} • lat ${data.lat ?? '--'}, lon ${data.lon ?? '--'}`; els.ci.textContent=data.carbonIntensity ?? '--'; els.provider.textContent=data._provider||'--'; els.verdict.textContent=rec.verdict||'--'; els.verdict.className=verdictClass(rec.verdict||''); els.reason.textContent=rec.reason||'--'; els.wait.textContent=rec.wait_hours ?? '--'; els.next.textContent=rec.next_best||'--'; }
    function applyTheme(mode){
      document.body.className = mode;
      els.theme.textContent = mode === 'dark' ? 'Light mode' : 'Dark mode';
      try { localStorage.setItem('pico_theme', mode); } catch (_) {}
    }
    function initTheme(){
      let mode = 'auto';
      try { mode = localStorage.getItem('pico_theme') || 'auto'; } catch (_) {}
      if (mode !== 'dark' && mode !== 'auto') mode = 'auto';
      applyTheme(mode);
    }
    async function load(){ try{ const res=await fetch('/status',{cache:'no-store'}); if(!res.ok)throw new Error('HTTP '+res.status); fill(await res.json()); }catch(err){ els.meta.textContent='Error loading /status: '+err.message; } }
    els.refresh.addEventListener('click', load);
    els.theme.addEventListener('click', ()=>applyTheme(document.body.className === 'dark' ? 'auto' : 'dark'));
    initTheme();
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>
"""


# TODO: THIS SHOULD HANDLE CEST/BST
def set_time(offset=0, delta=2208988800, host="pool.ntp.org"):
    NTP_QUERY = bytearray(48)
    NTP_QUERY[0] = 0x1B
    addr = socket.getaddrinfo(host, 123)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1)
        s.sendto(NTP_QUERY, addr)
        msg = s.recv(48)
    finally:
        s.close()
    val = struct.unpack("!I", msg[40:44])[0]
    t = val - delta
    tm = time.gmtime(t+offset)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    log("Local time:", _now_stamp())


def handle_http_request(conn):
    global LOGGER
    if conn is None:
        return

    request = parse_request(conn)
    if not request:
        return

    method, path_qs = request
    path, params = split_path_qs(path_qs)

    try:
        process_http_request(conn, method, path, params)
    except Exception as error:
        crash_path = write_crashdump(error, context="http")
        LOGGER.exception("ERROR", error, crash_path)
        append_log_line("ERROR %s" % crash_path)
        send_json(conn, 500, {"error": "Internal error", "details": str(error)})
    finally:
        try:
            conn.close()
        except Exception:
            pass

def process_http_request(conn, method, path, params):
    if method != "GET":
        return send_json(conn, 405, {"error": "Only GET supported"})

    if path == "/html":
        return send_html(conn, 200, build_index_html())
    if path == "/em/window":
        return send_json(conn, 200, handle_em_window(params))
    if path == "/em/window-overlay":
        return send_json(conn, 200, handle_em_overlay(params))
    if path == "/status":
        return send_json(conn, 200, handle_status(params))

    send_json(conn, 404, {"error": "Not found", "path": path})

def get_connection():
    if _server_socket is None:
        return None
    try:
        conn, _ = _server_socket.accept()
        return conn
    except OSError:
        return None

def open_socket(ip):
    global _server_socket

    addr = socket.getaddrinfo(CONFIG.server.host, CONFIG.server.port)[0][-1]
    _server_socket = socket.socket()
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(addr)
    _server_socket.listen(2)
    _server_socket.settimeout(1)
    log("Pico running: http://%s:%d" % (ip, CONFIG.server.port))


def serve_forever(ip):
    global _epd

    open_socket(ip)
    _epd = get_epd()

    render_placeholder_screen("BOOT", "Waiting for data...")
    while True:
        _display_tick()

        conn = get_connection()
        handle_http_request(conn)

