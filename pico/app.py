import time

from diagnostics import boot_lines, format_location, geo_summary
from fw_providers import fetch_window_any
from recommendation import recommend_from_week
from timeutil import WEEK_SECONDS
from ttl_cache import TtlCache
from uptime import UPTIME
from utils import (
    ProviderError,
    epoch_to_iso_z,
    floor_hour_epoch,
    http_get_json,
    iso_z_to_epoch,
    log,
    safe_float,
    url_decode,
)

from config import CONFIG

# Read by fw_render: a window that came from a provider rather than the cache
# means the panel is redrawn from white instead of over the last frame.
_fresh_data = False

_cache = TtlCache(CONFIG.cache_refresh_seconds)
_auto_geo_cache = None
_auto_geo_expires = 0
# Coarse geolocation for the logs and /status. Never holds coordinates.
_geo_details = {}
_last_provider_used = "unknown"


def _geo_from_payload(payload):
    """The four fields the grid lookup needs, or a ProviderError saying which
    part of the payload was unusable. Pure: the cache and the retry cooldown
    stay with the caller."""
    if payload.get("success") is False:
        raise ProviderError("IP geo lookup failed")

    lat = safe_float(payload.get("latitude"))
    lon = safe_float(payload.get("longitude"))
    city = (payload.get("city") or payload.get("region") or "").strip()
    cc = (payload.get("country_code") or "").strip().upper()

    if lat is None or lon is None or not city or not cc:
        raise ProviderError("IP geo incomplete payload")

    return {"lat": lat, "lon": lon, "city": city, "cc": cc}


def _auto_geo_defaults():
    global _auto_geo_cache, _auto_geo_expires, _geo_details

    if not CONFIG.geo.auto_from_public_ip:
        return None

    now = time.time()
    if _auto_geo_cache and now < _auto_geo_expires:
        return _auto_geo_cache

    try:
        payload = http_get_json(CONFIG.geo.ip_lookup_url, "IP geo")
        _auto_geo_cache = _geo_from_payload(payload)
        _auto_geo_expires = now + int(CONFIG.geo.refresh_seconds)
        # Coarse on purpose: logs get pasted into issues, and a precise
        # coordinate is a home address. The exact figures stay in the cache
        # above, where the grid lookup needs them.
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

# A plausible day of intensities; the dummy provider draws uniformly between
# this seed's own minimum and maximum.
DUMMY_SERIES_SEED = [430, 410, 395, 380, 360, 345, 330, 320, 315, 325, 340, 365]


def _rand01():
    global _dummy_rng_state
    # Deterministic LCG; avoids depending on CPython random module in MicroPython.
    _dummy_rng_state = (1103515245 * _dummy_rng_state + 12345) & 0x7FFFFFFF
    return (_dummy_rng_state % 10000) / 10000.0


def dummy_fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del lat, lon, city, country_code
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


def _fetch_window(lat, lon, city, cc, start_epoch, end_epoch):
    """The cache miss path for `get_window`. Only called through it."""
    global _fresh_data, _last_provider_used
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


def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    global _fresh_data
    key = ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)
    _fresh_data = False
    return _cache.get_or_set(
        key, lambda: _fetch_window(lat, lon, city, cc, start_epoch, end_epoch)
    )


def handle_em_window(params):
    now = floor_hour_epoch(int(time.time()))
    back_hours = int(params.get("back_hours") or CONFIG.timeline.back_hours_default)
    lat, lon, city, cc = resolve_geo(params)
    return get_window(lat, lon, city, cc, now - back_hours * 3600, now)


def handle_em_overlay(params):
    now = floor_hour_epoch(int(time.time()))
    lat, lon, city, cc = resolve_geo(params)
    # Previous-week window matching [-48h, +12h] of the current timeline.
    start = now - WEEK_SECONDS - (CONFIG.timeline.back_hours_default * 3600)
    end = now - WEEK_SECONDS + (CONFIG.timeline.future_hours * 3600)
    return get_window(lat, lon, city, cc, start, end)


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
    return _cache.get_or_set(key, lambda: build_status_bundle(params)[0])


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
