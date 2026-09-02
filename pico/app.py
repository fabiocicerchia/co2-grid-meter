import time

from diagnostics import boot_lines, format_location, geo_summary
from display import (
    EINK_BLACK,
    draw_current_panel,
    draw_graph,
    draw_leds,
    draw_rect,
    draw_text,
    draw_time,
    draw_wifi_icon,
    epd_clear_screen,
    get_epd,
    intensity_zone_from_percentile,
    led_level_from_percentile,
    panel_dimensions,
)
from export import summary_from_window, window_csv
from fetcher import BackgroundFetcher
from fw_network import wifi_ok, wifi_signal_bars
from fw_providers import fetch_window_any
from i18n import t
from recommendation import recommend_from_week
from ttl_cache import TtlCache
from uptime import UPTIME
from utils import (
    ProviderError,
    epoch_to_iso_z,
    floor_hour_epoch,
    fmt_hhmm_local,
    free_mem,
    http_get_json,
    iso_z_to_epoch,
    log,
    percentile,
    safe_float,
    url_decode,
)

from config import CONFIG

_epd = None
_last_render = 0
_cache = TtlCache(CONFIG.cache_refresh_seconds)
# Provider I/O only. Everything else — status composition, geo lookups — stays
# on TtlCache: it is cheap and local, and a second thread for it would cost a
# stack for no stall removed.
_fetcher = BackgroundFetcher(CONFIG.cache_refresh_seconds)
_auto_geo_cache = None
_auto_geo_expires = 0
# Coarse geolocation for the logs and /status. Never holds coordinates.
_geo_details = {}
_last_provider_used = "unknown"


def _auto_geo_defaults():
    global _auto_geo_cache, _auto_geo_expires

    if not CONFIG.geo.auto_from_public_ip:
        return None

    now = time.time()
    if _auto_geo_cache and now < _auto_geo_expires:
        return _auto_geo_cache

    try:
        payload = http_get_json(CONFIG.geo.ip_lookup_url, "IP geo")
        if payload.get("success") is False:
            raise ProviderError("IP geo lookup failed")

        lat = safe_float(payload.get("latitude"))
        lon = safe_float(payload.get("longitude"))
        city = (payload.get("city") or payload.get("region") or "").strip()
        cc = (payload.get("country_code") or "").strip().upper()

        if lat is None or lon is None or not city or not cc:
            raise ProviderError("IP geo incomplete payload")

        _auto_geo_cache = {"lat": lat, "lon": lon, "city": city, "cc": cc}
        _auto_geo_expires = now + int(CONFIG.geo.refresh_seconds)
        # Coarse on purpose: logs get pasted into issues, and a precise
        # coordinate is a home address. The exact figures stay in the cache
        # above, where the grid lookup needs them.
        global _geo_details
        _geo_details = geo_summary(payload)
        log("Auto-geo resolved to %s" % format_location(_geo_details))
        if _geo_details.get("isp"):
            log("ISP: %s" % _geo_details["isp"])
        return _auto_geo_cache
    except Exception as error:
        log("Auto-geo failed: %s" % error)
        _auto_geo_expires = now + int(CONFIG.geo.failure_retry_seconds)
        return _auto_geo_cache


def log_boot_diagnostics():
    """Resolve geolocation once at boot and log what was found.

    Called from main so the answer is in the log before the first request,
    rather than appearing whenever a browser happens to hit /status. A failed
    lookup is a warning and nothing more: the device still serves, falling back
    to the configured defaults, and saying so is more useful than refusing to
    boot over it.
    """
    try:
        _auto_geo_defaults()
    except Exception as error:  # never let diagnostics stop the boot
        log("Auto-geo unavailable: %s" % error)
    summary = diagnostics_summary()
    for line in boot_lines(summary["network"], summary["location"]):
        log(line)


def diagnostics_summary():
    """Coarse location, ISP and interface — the boot log, as JSON."""
    try:
        from fw_network import interface_summary

        net = interface_summary()
    except Exception:
        # Not running on a Pico (mock/dev server): the geo half still applies.
        net = {}
    return {"network": net, "location": dict(_geo_details)}


def resolve_geo(params):
    lat = safe_float(params.get("lat")) if params else None
    lon = safe_float(params.get("lon")) if params else None
    city = url_decode(params.get("city")) if params else None
    cc = url_decode(params.get("cc")) if params else None

    auto_geo = _auto_geo_defaults() or {
        "lat": CONFIG.defaults.latitude,
        "lon": CONFIG.defaults.longitude,
        "city": CONFIG.defaults.city,
        "cc": CONFIG.defaults.country,
    }

    return (
        lat if lat is not None else auto_geo["lat"],
        lon if lon is not None else auto_geo["lon"],
        city if city else auto_geo["city"],
        cc.upper() if cc else auto_geo["cc"],
    )


def series_values(series_json):
    out = []
    for p in series_json.get("history") or []:
        v = safe_float(p.get("carbonIntensity"))
        if v is not None:
            out.append(v)
    return out


def series_points(series_json):
    points = []
    for p in series_json.get("history") or []:
        ts = iso_z_to_epoch(p.get("datetime"))
        v = safe_float(p.get("carbonIntensity"))
        if ts is not None and v is not None:
            points.append((floor_hour_epoch(ts), v))
    points.sort(key=lambda item: item[0])
    return points


# TODO: add a variable to force switch the provide and the city
_dummy_rng_state = int(time.time()) & 0x7FFFFFFF


def _rand01():
    global _dummy_rng_state
    # Deterministic LCG; avoids depending on CPython random module in MicroPython.
    _dummy_rng_state = (1103515245 * _dummy_rng_state + 12345) & 0x7FFFFFFF
    return (_dummy_rng_state % 10000) / 10000.0


def dummy_fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del lat, lon, city, country_code
    DUMMY_SERIES_SEED = [430, 410, 395, 380, 360, 345, 330, 320, 315, 325, 340, 365]
    min_ci = min(DUMMY_SERIES_SEED)
    max_ci = max(DUMMY_SERIES_SEED)

    history = []
    cursor = floor_hour_epoch(int(start_epoch))
    end_h = floor_hour_epoch(int(end_epoch))
    while cursor <= end_h:
        value = int(round(min_ci + _rand01() * (max_ci - min_ci)))
        history.append({"datetime": epoch_to_iso_z(cursor), "carbonIntensity": value})
        cursor += 3600

    if history:
        log(
            "DUMMY provider generated %d points in range [%d, %d]"
            % (len(history), min_ci, max_ci)
        )
    return {"city": "Dummy", "history": history, "_provider": "dummy"}, "dummy"


_fresh_data = False
# The publish time of the reading the screen was last drawn from. A change in
# it means a new reading arrived, which is when a full e-ink clear is worth its
# flicker — "did this call do the fetching" stopped being the same question
# once fetching moved off the request path.
_last_window_stamp = 0


def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    global _fresh_data, _last_window_stamp
    key = ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)

    def fetch():
        global _last_provider_used
        log("Fetching data...")
        if CONFIG.providers.force_dummy:
            data, provider_used = dummy_fetch_window_any(
                lat, lon, city, cc, start_epoch, end_epoch
            )
        else:
            data, provider_used = fetch_window_any(
                lat, lon, city, cc, start_epoch, end_epoch
            )
        log("Provider used: %s" % provider_used)
        data["_provider"] = provider_used
        _last_provider_used = provider_used
        data["lat"] = lat
        data["lon"] = lon
        data["_resolved"] = {"city": city, "cc": cc}
        return data

    # Starting here rather than in main(): app.py is imported lazily, start()
    # is idempotent, and a device whose thread cannot start still serves — the
    # fetcher falls back to fetching inline.
    _fetcher.start()
    data = _fetcher.get_or_set(key, fetch)
    if data is None:
        # Nothing has ever been fetched for this window and the first attempt
        # did not finish in time. Raised, not returned empty: every caller
        # already handles a provider failure, and "warming up" is one.
        raise ProviderError("No reading yet — the first fetch is still running")

    published_at, _ = _fetcher.published(key)
    _fresh_data = published_at != _last_window_stamp
    _last_window_stamp = published_at
    return data


def handle_em_window(params):
    now = floor_hour_epoch(int(time.time()))
    back_hours = int(params.get("back_hours") or CONFIG.timeline.back_hours_default)
    lat, lon, city, cc = resolve_geo(params)
    return get_window(lat, lon, city, cc, now - back_hours * 3600, now)


def handle_em_overlay(params):
    now = floor_hour_epoch(int(time.time()))
    lat, lon, city, cc = resolve_geo(params)
    # Previous-week window matching [-48h, +12h] of the current timeline.
    start = now - (7 * 24 * 3600) - (CONFIG.timeline.back_hours_default * 3600)
    end = now - (7 * 24 * 3600) + (CONFIG.timeline.future_hours * 3600)
    return get_window(lat, lon, city, cc, start, end)


# ---- Export endpoints (for home automation, not the dashboard) ----
# The shaping lives in pico/export.py so it can be tested under CPython; these
# two are the wiring that gives it the data.


def handle_em_window_csv(params):
    return window_csv(handle_em_window(params))


def handle_em_summary(params):
    status, window_data, _ = build_status_bundle(params)
    return summary_from_window(
        window_data,
        status.get("carbonIntensity"),
        status.get("recommendation"),
        status.get("datetime"),
        city=status.get("city"),
        cc=status.get("cc"),
        provider=status.get("_provider"),
        uptime_seconds=status.get("uptime_seconds"),
    )


def make_next_line(recommendation):
    wait_hours = recommendation.get("wait_hours")
    if isinstance(wait_hours, int) and wait_hours > 0:
        return t(
            "label.wait_hours",
            wait_hours,
            fmt_hhmm_local(int(time.time()) + wait_hours * 3600),
        )
    return (recommendation.get("reason") or "").strip()[
        :22
    ]  # TODO: THIS LINE IS NOT REALLY NEEDED


def build_status_bundle(params):
    log("Fetching data")
    lat, lon, city, cc = resolve_geo(params)
    now = floor_hour_epoch(int(time.time()))

    window_data = handle_em_window(
        {
            "lat": str(lat),
            "lon": str(lon),
            "city": city,
            "cc": cc,
            "back_hours": str(CONFIG.timeline.back_hours_default),
        }
    )
    history = window_data.get("history") or []
    if not history:
        raise ProviderError("No window history")

    current_intensity = safe_float(history[-1].get("carbonIntensity"))
    if current_intensity is None:
        raise ProviderError("No carbonIntensity in last point")

    overlay_data = handle_em_overlay(
        {"lat": str(lat), "lon": str(lon), "city": city, "cc": cc}
    )
    recommendation = recommend_from_week(
        current_intensity,
        overlay_data.get("history") or [],
        CONFIG.timeline.future_hours,
    )
    log("Finished fetching data")

    status = {
        "datetime": epoch_to_iso_z(now),
        "lat": lat,
        "lon": lon,
        "city": city,
        "cc": cc,
        "carbonIntensity": current_intensity,
        "recommendation": recommendation,
        "_provider": window_data.get("_provider") or "—",
        # Same diagnostics the boot log prints: coarse location, ISP and the
        # interface. No coordinates, no credentials — see pico/diagnostics.py.
        "diagnostics": diagnostics_summary(),
        # Raw seconds, not a formatted string: the caller is a machine, and a
        # monotonic count is the only thing that survives an unset RTC.
        "uptime_seconds": UPTIME.seconds(),
    }

    return status, window_data, overlay_data


def handle_status(params):
    lat, lon, city, cc = resolve_geo(params)
    # Keep a stable key so /status serves cached payload immediately when present.
    # Freshness is managed by TtlCache(CONFIG.cache_refresh_seconds).
    key = ("status", round(lat, 4), round(lon, 4), city, cc)

    def build():
        status, _, _ = build_status_bundle(params)
        return status

    return _cache.get_or_set(key, build)


# ---- Periodic e-ink refresh (decoupled from HTTP polling) ----
_last_display_tick = 0


def _ota_status():
    # Imported here, not at module scope: a device flashed before OTA existed
    # has no ota.py, and /status must still answer.
    try:
        import ota

        return ota.status()
    # Broad on purpose: diagnostics never break the endpoint.
    except Exception:
        return {"stage": "unavailable"}


def _display_tick():
    """Refresh the e-ink every CONFIG.display.render_min_interval_sec even if /status is never called."""
    global _last_display_tick
    now = int(time.time())
    if now - _last_display_tick < CONFIG.display.render_min_interval_sec:
        log("Wait...")
        return
    _last_display_tick = now

    # Choose default params for your device (same as you use when calling /status)
    # If you already have a default location mechanism, use that.
    params = {}  # or {"city": "..."} etc, whatever resolve_geo() supports

    try:
        status, window_data, overlay_data = build_status_bundle(params)
        render_screen(status, window_data, overlay_data)
    except Exception as e:
        # Don't crash the server loop if provider/network is down
        try:
            log("ERROR(_display_tick) %s" % e)
            render_placeholder_screen("DATA ERROR", str(e))
        except Exception as e:
            log("ERROR(_display_tick 2) %s" % e)


def draw_top_bar(_epd):
    draw_wifi_icon(_epd, 180, 5, wifi_ok(), wifi_signal_bars())
    draw_time(_epd, 205, 8)


def render_placeholder_screen(title, detail):
    global _epd, _has_rendered_data
    _epd = get_epd()

    epd_clear_screen(_epd)
    screen_w, _ = panel_dimensions(_epd)
    panel_w = max(40, screen_w - 10)
    draw_rect(_epd.black_frame, 5, 20, panel_w, 25, color=EINK_BLACK, fill=False)

    title = title or "Status"
    draw_text(_epd.black_frame, 10, 28, title, color=EINK_BLACK)

    if detail:
        detail_text = str(detail)
        if title == "DATA ERROR":
            # Show the error across two lines for readability on failure screen.
            draw_text(_epd.red_frame, 5, 50, detail_text[:50], color=EINK_BLACK)
            draw_text(_epd.red_frame, 5, 57, detail_text[51:10], color=EINK_BLACK)
        else:
            draw_text(_epd.black_frame, 5, 50, str(detail), color=EINK_BLACK)
    draw_top_bar(_epd)
    _epd.display()


def _current_ip(wifi_connected_callback):
    if not wifi_connected_callback():
        return None
    try:
        import network

        wlan = network.WLAN(network.STA_IF)
        return wlan.ifconfig()[0]
    except Exception:
        return None


def handle_system_info(params, wifi_connected_callback):
    lat, lon, city, cc = resolve_geo(params)
    return {
        "wifi_connected": bool(wifi_connected_callback()),
        "ip": _current_ip(wifi_connected_callback),
        "city": city,
        "country": cc,
        "lat": lat,
        "lon": lon,
        "provider_last_used": _last_provider_used,
        # What the background fetcher is doing: whether the worker is up, how
        # many fetches it has run and the last error it swallowed. Without this
        # a stuck provider is invisible — the page keeps serving the last good
        # reading, which is the point, and also how you fail to notice.
        "fetcher": _fetcher.stats(),
        # An update that rolled itself back silently is the one you discover
        # weeks later, wondering why a fix never took.
        "ota": _ota_status(),
    }


def render_screen(status_json, window_json, overlay_json):
    global _epd, _last_render
    now = int(time.time())
    if now - _last_render < CONFIG.display.render_min_interval_sec:
        log("Wait...")
        return
    _epd = get_epd()

    current_intensity = safe_float(status_json.get("carbonIntensity")) or 0.0
    recommendation = status_json.get("recommendation") or {}
    verdict = recommendation.get("verdict") or "—"
    next_line = make_next_line(recommendation)

    now_epoch = floor_hour_epoch(int(time.time()))
    current_points = series_points(window_json)
    overlay_points = series_points(overlay_json)

    # Build aligned 60-hour timeline: [-48h, +12h]
    timeline = [
        now_epoch - (CONFIG.timeline.back_hours_default * 3600) + i * 3600
        for i in range(60)
    ]
    current_map = {ts: v for ts, v in current_points}
    week_map = {ts + (7 * 24 * 3600): v for ts, v in overlay_points}
    current_line = [current_map.get(ts) for ts in timeline]
    week_line = [week_map.get(ts) for ts in timeline]

    overlay_values = [v for _, v in overlay_points]
    percentile_value = (
        percentile(sorted(overlay_values), current_intensity)
        if len(overlay_values) >= 12
        else None
    )
    zone = intensity_zone_from_percentile(percentile_value)
    level = led_level_from_percentile(percentile_value)

    if _fresh_data:
        epd_clear_screen(_epd)

    draw_leds(_epd, zone, level)
    draw_current_panel(_epd, current_intensity, verdict, next_line)
    draw_graph(_epd, current_line, week_line)
    draw_top_bar(_epd)

    _epd.display()
    _last_render = now

    free_mem()
