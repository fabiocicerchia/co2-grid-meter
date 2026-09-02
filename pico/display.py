import time

import framebuf
import utime
from i18n import t
from machine import SPI, Pin
from utils import clamp, log

from config import CONFIG

EINK_BLACK = 0
EINK_WHITE = 1


EPD_WIDTH = 122
EPD_HEIGHT = 250
RST_PIN = 12
DC_PIN = 8
CS_PIN = 9
BUSY_PIN = 13

# The LED bar drawn top-left, and the number of levels a percentile maps onto.
LED_COUNT = 8


class EPD_2in13_B_V4_Base:
    def __init__(self):
        self.reset_pin = Pin(RST_PIN, Pin.OUT)

        self.busy_pin = Pin(BUSY_PIN, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(CS_PIN, Pin.OUT)
        if EPD_WIDTH % 8 == 0:
            self.width = EPD_WIDTH
        else:
            self.width = (EPD_WIDTH // 8) * 8 + 8
        self.height = EPD_HEIGHT

        self.spi = SPI(1)
        self.spi.init(baudrate=4000_000)
        self.dc_pin = Pin(DC_PIN, Pin.OUT)

        self.buffer_black = bytearray(self.height * self.width // 8)
        self.buffer_red = bytearray(self.height * self.width // 8)

    def init(self):
        log("Init e-ink")
        self.reset()

        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()

        self.send_command(0x01)  # Driver output control
        self.send_data(0xF9)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x11)  # data entry mode
        self.send_data(self.command_code)

        self.SetWindows(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)

        self.send_command(0x3C)  # BorderWaveform
        self.send_data(0x05)

        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x21)  #  Display update control
        self.send_data(0x80)
        self.send_data(0x80)

        self.ReadBusy()

        return 0

    def digital_write(self, pin, value):
        pin.value(value)

    def digital_read(self, pin):
        return pin.value()

    def delay_ms(self, delaytime):
        utime.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    def module_exit(self):
        self.digital_write(self.reset_pin, 0)

    # Hardware reset
    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)

    def send_command(self, command):
        self.digital_write(self.dc_pin, 0)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([command])
        self.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([data])
        self.digital_write(self.cs_pin, 1)

    def send_data1(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        while self.digital_read(self.busy_pin) == 1:
            self.delay_ms(10)
        self.delay_ms(20)

    def TurnOnDisplay(self):
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        self.send_command(0x44)  # SET_RAM_X_ADDRESS_START_END_POSITION
        self.send_data((Xstart >> 3) & 0xFF)
        self.send_data((Xend >> 3) & 0xFF)

        self.send_command(0x45)  # SET_RAM_Y_ADDRESS_START_END_POSITION
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)
        self.send_data(Yend & 0xFF)
        self.send_data((Yend >> 8) & 0xFF)

    def SetCursor(self, Xstart, Ystart):
        self.send_command(0x4E)  # SET_RAM_X_ADDRESS_COUNTER
        self.send_data(Xstart & 0xFF)

        self.send_command(0x4F)  # SET_RAM_Y_ADDRESS_COUNTER
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)

    def Clear(self, colorblack, colorred):
        self.send_command(0x24)
        self.send_data1([colorblack] * self.height * int(self.width / 8))

        self.send_command(0x26)
        self.send_data1([colorred] * self.height * int(self.width / 8))

        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0x10)
        self.send_data(0x01)

        self.delay_ms(2000)
        self.module_exit()

    def display(self):
        self.send_command(0x24)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(self.height):
                self.send_data(self.buffer_black[i + j * self.height])

        self.send_command(0x26)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(self.height):
                self.send_data(self.buffer_red[i + j * self.height])

        self.TurnOnDisplay()


# TODO: TEST IT
class EPD_2in13_B_V4_Portrait(EPD_2in13_B_V4_Base):
    def __init__(self):
        super().__init__()

        self.command_code = 0x03

        self.imageblack = framebuf.FrameBuffer(
            self.buffer_black, self.width, self.height, framebuf.MONO_HLSB
        )
        self.imagered = framebuf.FrameBuffer(
            self.buffer_red, self.width, self.height, framebuf.MONO_HLSB
        )
        self.init()


class EPD_2in13_B_V4_Landscape(EPD_2in13_B_V4_Base):
    def __init__(self):
        super().__init__()

        self.command_code = 0x07

        self.imageblack = framebuf.FrameBuffer(
            self.buffer_black, self.height, self.width, framebuf.MONO_VLSB
        )
        self.imagered = framebuf.FrameBuffer(
            self.buffer_red, self.height, self.width, framebuf.MONO_VLSB
        )
        self.init()


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

    def _draw_verdict_line(x, y, text):
        draw_text_bold(text_frame, x, y, text, color=text_color)

    if warning_mode:
        _draw_verdict_line(text_x, text_y, next_line)
    else:
        _draw_verdict_line(text_x, text_y, verdict)

    draw_text(epd.black_frame, 5, 47, t("label.co2", int(current_ci)))


def draw_graph(epd, current_line, week_line):
    graph_hours = CONFIG.timeline.back_hours_default + CONFIG.timeline.future_hours
    if not current_line and not week_line:
        draw_rect(epd.black_frame, 5, 55, 112, 80, color=0, fill=False)
        return

    screen_w, screen_h = panel_dimensions(epd)

    base_x, base_y = 5, 60
    width = max(10, screen_w - 10)
    height = max(10, min(90, screen_h - base_y - 5))

    if not current_line and not week_line:
        draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)
        return

    tick_band = 9
    plot_h = max(8, height - tick_band)
    draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)

    # Y-scale from min/max over last week + current timeline values.
    scale_values = [v for v in current_line + week_line if isinstance(v, (int, float))]
    if not scale_values:
        return
    low, high = min(scale_values), max(scale_values)

    def norm(v):
        if v is None:
            return None
        if high == low:
            return 0.5
        return (v - low) / (high - low)

    normalized_current = [norm(v) for v in current_line]
    normalized_week = [norm(v) for v in week_line]

    npts = min(graph_hours, max(len(normalized_current), len(normalized_week)))
    if npts < 2:
        return

    inner_w = max(1, width - 2)
    step_x = inner_w / float(max(1, npts - 1))

    def x_at(i):
        return base_x + 1 + int(round(i * step_x))

    def y_from_norm(n):
        n = min(1.0, max(0.0, n))
        return base_y + (plot_h - 2) - int(round(n * (plot_h - 3)))

    def draw_line(target_frame, values, dotted=False):
        for i in range(npts - 1):
            a = values[i] if i < len(values) else None
            b = values[i + 1] if i + 1 < len(values) else None
            if a is None or b is None:
                continue
            x1, y1 = x_at(i), y_from_norm(a)
            x2, y2 = x_at(i + 1), y_from_norm(b)
            if not dotted:
                target_frame.line(x1, y1, x2, y2, EINK_BLACK)
                continue
            dx, dy = x2 - x1, y2 - y1
            steps = max(abs(dx), abs(dy))
            if steps <= 0:
                continue
            for s in range(0, steps + 1, 2):
                px = x1 + (dx * s) // steps
                py = y1 + (dy * s) // steps
                target_frame.pixel(px, py, EINK_BLACK)

    # Current timeline: solid black. Previous-week timeline: dotted black.
    draw_line(epd.black_frame, normalized_current, dotted=False)
    draw_line(epd.black_frame, normalized_week, dotted=True)

    # Red dashed threshold bands (percentile cutoffs) across the graph.
    def draw_dashed_hline(x0, x1, y, dash=3, gap=5):
        x = int(x0)
        x1 = int(x1)
        y = int(y)
        while x <= x1:
            seg_end = min(x + dash - 1, x1)
            seg_w = max(1, seg_end - x + 1)

            epd.black_frame.hline(x, y, seg_w, EINK_WHITE)
            epd.red_frame.hline(x, y, seg_w, EINK_BLACK)
            x = seg_end + gap + 1

    def value_at_percentile(sorted_values, p):
        if not sorted_values:
            return None
        p = min(1.0, max(0.0, float(p)))
        if len(sorted_values) == 1:
            return sorted_values[0]
        pos = p * (len(sorted_values) - 1)
        lo = int(pos)
        hi = lo + 1
        if hi >= len(sorted_values):
            return sorted_values[lo]
        frac = pos - lo
        return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac

    threshold_percentiles = (
        CONFIG.thresholds.green_percentile_max,
        CONFIG.thresholds.yellow_percentile_max,
    )
    sorted_scale = sorted(scale_values)
    x0 = base_x + 1
    x1 = base_x + width - 2
    for p in threshold_percentiles:
        v = value_at_percentile(sorted_scale, p)
        if v is None:
            continue
        draw_dashed_hline(x0, x1, y_from_norm(norm(v)))

    # "now" marker line
    now_idx = CONFIG.timeline.back_hours_default
    if 0 <= now_idx < npts:
        draw_vline(
            epd.black_frame,
            x_at(now_idx),
            base_y + 1,
            max(1, plot_h - 1),
            color=EINK_BLACK,
        )

    # Day ticks and labels (-48h, -24h, now)
    tick_y0 = base_y + plot_h
    tick_y1 = base_y + height - 2
    labels = [(-48, "-2d"), (-24, "-1d"), (0, "now")]
    for hour_offset, label in labels:
        idx = hour_offset + CONFIG.timeline.back_hours_default
        if idx < 0 or idx >= npts:
            continue
        x = x_at(idx)
        draw_vline(
            epd.black_frame, x, tick_y0, max(1, tick_y1 - tick_y0 + 1), color=EINK_BLACK
        )
        draw_text(
            epd.black_frame,
            max(base_x + 1, x - 8),
            base_y + height - 8,
            label,
            color=EINK_BLACK,
        )
