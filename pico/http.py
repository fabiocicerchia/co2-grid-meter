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
from timeutil import utc_offset_seconds
from utils import _now_stamp, log

from config import CONFIG, append_log_line, write_crashdump

_server_socket = None

_MINI_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>CO₂ Pico</title></head>
<body><h3>Pico local pages</h3><ul><li><a href='/html/graph'>Graph</a></li><li><a href='/system-info'>System info JSON</a></li></ul></body></html>"""

_GRAPH_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>CO₂ graph</title></head>
<body><h3>Last 48h CO₂ (gCO₂/kWh)</h3><canvas id='c' width='640' height='280' style='border:1px solid #ccc'></canvas>
<script>
fetch('/em/window?back_hours=48').then(r=>r.json()).then(j=>{
 const h=(j.history||[]).map(x=>Number(x.carbonIntensity)).filter(Number.isFinite);
 const c=document.getElementById('c'),ctx=c.getContext('2d'); if(!h.length){ctx.fillText('No data',10,20);return;}
 const mn=Math.min(...h),mx=Math.max(...h),w=c.width,hg=c.height,pad=20;
 ctx.beginPath(); h.forEach((v,i)=>{const x=pad+i*(w-2*pad)/Math.max(1,h.length-1);const y=hg-pad-((v-mn)/(Math.max(1,mx-mn)))*(hg-2*pad); i?ctx.lineTo(x,y):ctx.moveTo(x,y)}); ctx.stroke();
});
</script></body></html>"""


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
    inm = ""
    while True:
        h = _readline(conn)
        if not h or h == b"\r\n":
            break
        # A header that is not valid UTF-8 is not one this server acts on, and
        # a malformed request must not take the connection down.
        line = h.decode("utf-8", "replace").strip()
        if line[:14].lower() == "if-none-match:":
            inm = line[14:].strip()
    return method, path_qs, inm


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


def set_time(offset=None, delta=2208988800, host="pool.ntp.org"):
    """Set the RTC from NTP, in local wall-clock time.

    `offset` is seconds to add to UTC. Left as None it is derived from
    `CONFIG.defaults.utc_offset_hours` plus EU summer time, so the clock is
    right on both sides of the March and October changes instead of running an
    hour out for seven months of the year.
    """
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
    if offset is None:
        # Decided from the UTC instant, never from the already-shifted one:
        # applying the rule to local time is what makes the repeated hour
        # ambiguous.
        offset = utc_offset_seconds(
            time.gmtime(t),
            standard_hours=CONFIG.defaults.utc_offset_hours,
            observes_dst=CONFIG.defaults.observes_eu_dst,
        )
    tm = time.gmtime(t + offset)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    log("Local time: %s (UTC%+d)" % (_now_stamp(), offset // 3600))


def handle_http_request(conn, LOGGER):
    if conn is None:
        return

    request = parse_request(conn)
    if not request:
        return

    method, path_qs, if_none_match = request
    path, params = split_path_qs(path_qs)
    LOGGER.info("%s %s" % (method, path))

    try:
        process_http_request(conn, method, path, params, if_none_match)
    except Exception as error:
        crash_path = write_crashdump(error, context="http")
        LOGGER.exception("ERROR %s %s" % (error, crash_path))
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
        return send_text(conn, 200, _MINI_HTML, "text/html")
    if path == "/html/graph":
        return send_text(conn, 200, _GRAPH_HTML, "text/html")

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


def get_connection(LOGGER):
    if _server_socket is None:
        return None
    try:
        conn, _ = _server_socket.accept()
        return conn
    except OSError as error:
        LOGGER.exception("OSError %s" % error)
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


def serve_forever(ip, LOGGER):
    global _epd

    open_socket(ip)
    _epd = get_epd()

    render_placeholder_screen("BOOT", "Waiting for data...")
    while True:
        try:
            ip = ensure_connected(ip)
            _display_tick()

            conn = get_connection(LOGGER)
            handle_http_request(conn, LOGGER)
        except Exception as error:
            log("serve_forever loop error: %s" % error)
            close_server_socket()
            time.sleep(1)
