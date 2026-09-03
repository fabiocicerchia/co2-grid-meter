"""What the e-ink shows: the timeline it draws and when it is redrawn.

Apart from `app.py` because the two answer different questions — app resolves
where the device is, calls providers and caches; this turns one of those
answers into a picture — and because rendering next to the logic it renders is
what made app.py a file with several jobs.

Imported by bare module name, like every other module under pico/ — see
CLAUDE.md.
"""

import time

# Both forms on purpose: the functions are bound once, but `app._fresh_data` is
# rewritten on every cache miss, so it has to be read through the module.
import app
from app import build_status_bundle, series_points
from display import (
    EINK_BLACK,
    draw_current_panel,
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
from fw_graph import draw_graph
from fw_network import wifi_ok, wifi_signal_bars
from i18n import t
from timeutil import WEEK_SECONDS
from utils import (
    floor_hour_epoch,
    fmt_hhmm_local,
    free_mem,
    log,
    percentile,
    safe_float,
)

from config import CONFIG

_epd = None
_last_render = 0

# One point per hour of the drawn timeline: 48 back plus 12 forward, matching
# the span draw_graph derives from CONFIG.timeline. Both have to move together.
TIMELINE_POINTS = 60


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
    except Exception as error:
        # Don't crash the server loop if provider/network is down
        try:
            log("ERROR(_display_tick) %s" % error)
            render_placeholder_screen("DATA ERROR", str(error))
        except Exception as render_error:
            log("ERROR(_display_tick 2) %s" % render_error)


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


def aligned_lines(window_json, overlay_json, now_epoch):
    """The two series the graph draws, sampled onto one 60-hour timeline.

    Both are placed on the same [-48h, +12h] grid so the week-shifted overlay
    sits under the current curve hour for hour; an hour neither provider
    covered is None, which the plot skips. Returns
    (current_line, week_line, overlay_values).
    """
    current_map = dict(series_points(window_json))
    overlay_points = series_points(overlay_json)
    week_map = {ts + WEEK_SECONDS: v for ts, v in overlay_points}

    timeline = [
        now_epoch - (CONFIG.timeline.back_hours_default * 3600) + i * 3600
        for i in range(TIMELINE_POINTS)
    ]
    return (
        [current_map.get(ts) for ts in timeline],
        [week_map.get(ts) for ts in timeline],
        [value for _, value in overlay_points],
    )


def week_percentile(current_intensity, overlay_values):
    """Where the current reading sits in the previous week's spread.

    None when half a day of overlay is missing: a percentile over four points
    is noise, and the LED bar and the zone both read better as "unknown".
    """
    if len(overlay_values) < 12:
        return None
    return percentile(sorted(overlay_values), current_intensity)


def render_screen(status_json, window_json, overlay_json):
    global _epd, _last_render
    now = int(time.time())
    if now - _last_render < CONFIG.display.render_min_interval_sec:
        log("Wait...")
        return
    _epd = get_epd()

    current_intensity = safe_float(status_json.get("carbonIntensity")) or 0.0
    recommendation = status_json.get("recommendation") or {}
    current_line, week_line, overlay_values = aligned_lines(
        window_json, overlay_json, floor_hour_epoch(now)
    )
    percentile_value = week_percentile(current_intensity, overlay_values)

    if app._fresh_data:
        epd_clear_screen(_epd)

    draw_leds(
        _epd,
        intensity_zone_from_percentile(percentile_value),
        led_level_from_percentile(percentile_value),
    )
    draw_current_panel(
        _epd,
        current_intensity,
        recommendation.get("verdict") or "—",
        make_next_line(recommendation),
    )
    draw_graph(_epd, current_line, week_line)
    draw_top_bar(_epd)

    _epd.display()
    _last_render = now

    free_mem()
