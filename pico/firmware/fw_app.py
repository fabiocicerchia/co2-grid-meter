"""Application-level data orchestration and endpoint handlers."""

import time

import fw_config
from fw_display import (
    EPD2in13BWR,
    draw_current_panel,
    draw_graph,
    draw_leds,
    draw_time,
    draw_wifi_icon,
    intensity_zone_from_percentile,
    led_level_from_percentile,
)
from fw_providers import fetch_window_any
from fw_recommendation import recommend_from_week
from fw_utils import (
    ProviderError,
    epoch_to_iso_z,
    floor_hour_epoch,
    fmt_hhmm_local,
    safe_float,
    url_decode,
)
from pico.ttl_cache import TtlCache
from pico.utils import percentile

_epd = None
_last_render = 0
_cache = TtlCache(getattr(fw_config.CONFIG, "cache_refresh_seconds", 3600))


def resolve_geo(params):
    latitude = safe_float(params.get("lat")) if params else None
    longitude = safe_float(params.get("lon")) if params else None
    city = url_decode(params.get("city")) if params else None
    country_code = url_decode(params.get("cc")) if params else None
    return (
        latitude if latitude is not None else fw_config.CONFIG.defaults.latitude,
        longitude if longitude is not None else fw_config.CONFIG.defaults.longitude,
        city if city else fw_config.CONFIG.defaults.city,
        country_code.upper() if country_code else fw_config.CONFIG.defaults.country,
    )


def series_values(series_json):
    values = []
    for point in series_json.get("history") or []:
        intensity_value = safe_float(point.get("carbonIntensity"))
        if intensity_value is not None:
            values.append(intensity_value)
    return values


def _window_cache_key(lat, lon, city, cc, start_epoch, end_epoch):
    return ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)


def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    cache_key = _window_cache_key(lat, lon, city, cc, start_epoch, end_epoch)

    def fetch():
        data, provider_used = fetch_window_any(lat, lon, city, cc, start_epoch, end_epoch)
        data["_provider"] = provider_used
        data["lat"] = lat
        data["lon"] = lon
        data["_resolved"] = {"city": city, "cc": cc}
        return data

    return _cache.get_or_set(cache_key, fetch)


def _timeline_window(params, start_epoch, end_epoch):
    lat, lon, city, cc = resolve_geo(params)
    return get_window(lat, lon, city, cc, start_epoch, end_epoch)


def handle_em_window(params):
    now = floor_hour_epoch(int(time.time()))
    back_hours = int(params.get("back_hours") or fw_config.CONFIG.timeline.back_hours_default)
    return _timeline_window(params, now - back_hours * 3600, now)


def handle_em_overlay(params):
    now = floor_hour_epoch(int(time.time()))
    start = now - (7 * 24 * 3600) - (fw_config.CONFIG.timeline.past_hours * 3600)
    end = now - (7 * 24 * 3600) + (fw_config.CONFIG.timeline.future_hours * 3600)
    return _timeline_window(params, start, end)


def make_next_line(recommendation):
    wait_hours = recommendation.get("wait_hours")
    if wait_hours is None:
        next_best = recommendation.get("next_best") or ""
        if next_best.startswith("in "):
            try:
                wait_hours = int(next_best.replace("in", "").replace("h", "").strip())
            except Exception:
                wait_hours = None

    if isinstance(wait_hours, int) and wait_hours > 0:
        eta = int(time.time()) + wait_hours * 3600
        return "Cleaner in %dh (%s)" % (wait_hours, fmt_hhmm_local(eta))

    reason = recommendation.get("reason") or ""
    next_best = recommendation.get("next_best") or ""
    return (reason + " " + next_best).strip()[:22]


def handle_status(params, wifi_connected_callback):
    lat, lon, city, cc = resolve_geo(params)
    now = floor_hour_epoch(int(time.time()))
    cache_key = ("status", round(lat, 4), round(lon, 4), city, cc, now)

    def build():
        window_data = handle_em_window(
            {
                "lat": str(lat),
                "lon": str(lon),
                "city": city,
                "cc": cc,
                "back_hours": str(fw_config.CONFIG.timeline.back_hours_default),
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
            fw_config.CONFIG.timeline.lookahead_hours,
        )

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

        try:
            render_screen(status, window_data, overlay_data, wifi_connected_callback)
        except Exception as error:
            print("[eink] render error:", error)
        return status

    return _cache.get_or_set(cache_key, build)


def render_screen(status_json, window_json, overlay_json, wifi_connected_callback):
    global _epd, _last_render

    now = int(time.time())
    if now - _last_render < fw_config.CONFIG.display.render_min_interval_sec:
        return

    if _epd is None:
        _epd = EPD2in13BWR()

    current_intensity = safe_float(status_json.get("carbonIntensity")) or 0.0
    recommendation = status_json.get("recommendation") or {}
    verdict = recommendation.get("verdict") or "—"
    next_line = make_next_line(recommendation)

    current_values = series_values(window_json)
    past_values = (
        current_values[-fw_config.CONFIG.timeline.past_hours :]
        if len(current_values) >= 2
        else []
    )

    overlay_values = series_values(overlay_json)
    future_values = (
        overlay_values[-fw_config.CONFIG.timeline.future_hours :]
        if len(overlay_values) >= 2
        else []
    )

    percentile_value = (
        percentile(sorted(overlay_values), current_intensity)
        if len(overlay_values) >= 12
        else None
    )
    zone = intensity_zone_from_percentile(percentile_value)
    level = led_level_from_percentile(percentile_value)

    _epd.clear()
    draw_leds(_epd, zone, level)
    draw_time(_epd, 160, 2)
    draw_wifi_icon(_epd, 194, 2, wifi_connected_callback())
    draw_current_panel(_epd, current_intensity, verdict, next_line)
    draw_graph(_epd, past_values, future_values)
    _epd.display()

    _last_render = now
