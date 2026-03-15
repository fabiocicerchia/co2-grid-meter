import time

from ttl_cache import TtlCache
from config import CONFIG
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
from fw_network import wifi_ok, wifi_signal_bars
from fw_providers import fetch_window_any
from recommendation import recommend_from_week
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


_epd = None
_last_render = 0
_cache = TtlCache(CONFIG.cache_refresh_seconds)
_auto_geo_cache = None
_auto_geo_expires = 0
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
        log("Auto-geo resolved to %s, %s (%s, %s)" % (city, cc, str(lat), str(lon)))
        return _auto_geo_cache
    except Exception as error:
        log("Auto-geo failed: %s" % error)
        _auto_geo_expires = now + int(CONFIG.geo.failure_retry_seconds)
        return _auto_geo_cache


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


def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    global _fresh_data, _last_provider_used
    key = ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)
    _fresh_data = False

    def fetch():
        global _fresh_data
        _fresh_data = True
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

    return _cache.get_or_set(key, fetch)


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


def make_next_line(recommendation):
    wait_hours = recommendation.get("wait_hours")
    if isinstance(wait_hours, int) and wait_hours > 0:
        return "WAIT %dh (%s)" % (
            wait_hours,
            fmt_hhmm_local(int(time.time()) + wait_hours * 3600),
        )
    return ((recommendation.get("reason") or "")).strip()[
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
            pass


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
