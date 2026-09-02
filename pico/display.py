import time

from epd_driver import EPD_2in13_B_V4_Landscape, EPD_2in13_B_V4_Portrait
from i18n import t
from utils import clamp, log

from config import CONFIG

EINK_BLACK = 0
EINK_WHITE = 1


# The LED bar drawn top-left, and the number of levels a percentile maps onto.
LED_COUNT = 8

# RENDERING

_epd = None


def get_epd():
    global _epd
    if _epd is None:
        if CONFIG.display.landscape:
            _epd = EPD_2in13_B_V4_Landscape()
        else:
            _epd = EPD_2in13_B_V4_Portrait()
        epd_bind_frames(_epd)

    return _epd


def epd_bind_frames(epd):
    """Normalize framebuffer attribute names across driver variants."""
    if not hasattr(epd, "black_frame"):
        fb = getattr(epd, "imageblack", None)
        if fb is not None:
            epd.black_frame = fb
    if not hasattr(epd, "red_frame"):
        fb = getattr(epd, "imagered", None)
        if fb is not None:
            epd.red_frame = fb

    if not hasattr(epd, "black_buffer"):
        buf = getattr(epd, "buffer_black", None)
        if buf is not None:
            epd.black_buffer = buf
    if not hasattr(epd, "red_buffer"):
        buf = getattr(epd, "buffer_red", None)
        if buf is not None:
            epd.red_buffer = buf


def epd_clear_screen(epd):
    """Compatibility clear across driver variants (clear vs Clear)."""
    log("Clearing e-ink")
    epd_bind_frames(epd)

    # Prefer direct framebuffer clear so backing buffers are always reset.
    if hasattr(epd, "black_frame") and hasattr(epd, "red_frame"):
        epd.black_frame.fill(EINK_WHITE)
        epd.red_frame.fill(EINK_WHITE)
        return

    clear_upper = getattr(epd, "Clear", None)
    if callable(clear_upper):
        # 0xFF = white for both planes in Waveshare reference driver.
        clear_upper(0xFF, 0xFF)
        return


def panel_dimensions(epd):
    frame = getattr(epd, "black_frame", None)
    frame_w = getattr(frame, "width", None)
    frame_h = getattr(frame, "height", None)
    if frame_w is not None and frame_h is not None:
        return int(frame_w), int(frame_h)

    width = int(getattr(epd, "width", 128))
    height = int(getattr(epd, "height", 250))
    if CONFIG.display.landscape:
        return height, width
    return width, height


def intensity_zone_from_percentile(percentile_value):
    if percentile_value is None:
        return "mid"
    if percentile_value <= CONFIG.thresholds.green_percentile_max:
        return "low"
    if percentile_value <= CONFIG.thresholds.yellow_percentile_max:
        return "mid"
    return "high"


def led_level_from_percentile(percentile_value):
    if percentile_value is None:
        return 0
    return int(clamp(int(round(percentile_value * LED_COUNT)), 0, LED_COUNT))


def draw_text(frame, x, y, text, color=0):
    # Use framebuf native font rendering (8px high) for speed and size.
    frame.text(str(text), int(x), int(y), color)


def draw_text_bold(frame, x, y, text, color=0):
    # Simulate bold by drawing twice with one-pixel horizontal offset.
    draw_text(frame, x, y, text, color=color)
    draw_text(frame, x + 1, y, text, color=color)


def draw_rect(frame, x, y, w, h, color=0, fill=False):
    if fill:
        frame.fill_rect(x, y, w, h, color)
    else:
        frame.rect(x, y, w, h, color)


def draw_vline(frame, x, y, h, color=0):
    frame.vline(x, y, h, color)


def draw_leds(epd, zone, level):
    fb = _fb(epd)
    # Draw 8 small "LED" blocks top-left
    # Clear the LED area first (white)
    start_x = 6
    start_y = 10
    fb.fill_rect(start_x, start_y, 56, 12, EINK_WHITE)
    for i in range(LED_COUNT):
        # filled black if ON, outline if OFF
        x = start_x + i * 7
        if i < int(level):
            fb.fill_rect(x, start_y, 6, 5, EINK_BLACK)
        else:
            fb.rect(x, start_y, 6, 5, EINK_BLACK)


def draw_wifi_icon(epd, x, y, connected, bars=0):
    frame = epd.black_frame if connected else epd.red_frame

    # Clear icon area (about 16x12)
    epd.black_frame.fill_rect(x, y, 16, 12, EINK_WHITE)
    epd.red_frame.fill_rect(x, y, 16, 12, EINK_WHITE)

    bars = int(clamp(int(bars), 0, 4)) if connected else 0

    # Bars from left to right (signal strength style)
    bar_w = 2
    gap = 1
    for i in range(4):
        bx = x + i * (bar_w + gap)
        bar_h = 3 + i * 2
        by = y + 11 - bar_h
        if i < bars:
            frame.fill_rect(bx, by, bar_w, bar_h, EINK_BLACK)
        else:
            epd.red_frame.rect(bx, by, bar_w, bar_h, EINK_BLACK)

    # Antenna dot
    if connected:
        frame.fill_rect(x + 13, y + 9, 2, 2, EINK_BLACK)
    else:
        frame.rect(x + 13, y + 9, 2, 2, EINK_BLACK)


def _fb(epd):
    # Always draw on the black layer framebuffer
    return epd.black_frame


def draw_time(epd, x, y):
    # Not `t`: that name is the i18n lookup imported at the top of this module.
    now_local = time.localtime()
    clock_text = "%02d:%02d" % (now_local[3], now_local[4])
    fb = _fb(epd)
    # Native framebuf text is 8x8 per character; clear only the printed area.
    text_w = len(clock_text) * 8
    text_h = 8
    fb.fill_rect(int(x), int(y), text_w, text_h, EINK_WHITE)
    draw_text(fb, x, y, clock_text)


def draw_current_panel(epd, current_ci, verdict, next_line):
    verdict = (verdict or "").strip()
    # Compared against the active locale, not the English literals: the verdict
    # arrives already translated, so hardcoding "OK"/"RUN NOW" put every
    # non-English device permanently in warning mode — on a clean grid too.
    warning_mode = verdict not in (t("verdict.ok"), t("verdict.run_now"))

    screen_w, _ = panel_dimensions(epd)
    panel_x, panel_y, panel_h = 5, 20, 25
    panel_w = max(40, screen_w - 10)

    # Clear panel area first.
    epd.black_frame.fill_rect(
        panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_WHITE
    )
    epd.red_frame.fill_rect(
        panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_WHITE
    )

    # Black background + white text.
    text_frame = epd.black_frame
    if warning_mode:
        # Red background + white text.
        text_frame = epd.red_frame
    text_frame.fill_rect(panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_BLACK)
    text_color = EINK_WHITE

    text_x = panel_x + 5
    text_y = panel_y + 8
    draw_text_bold(
        text_frame,
        text_x,
        text_y,
        next_line if warning_mode else verdict,
        color=text_color,
    )

    draw_text(epd.black_frame, 5, 47, t("label.co2", int(current_ci)))
