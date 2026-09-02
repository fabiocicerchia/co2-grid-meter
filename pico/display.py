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

# Graph geometry, in pixels. The band at the bottom is left free for the day
# ticks; the dash pattern is the red percentile bands.
GRAPH_ORIGIN = (5, 60)
GRAPH_TICK_BAND = 9
GRAPH_DASH_LEN = 3
GRAPH_DASH_GAP = 5
# Day ticks: hours relative to now, and the label drawn under each.
GRAPH_DAY_TICKS = ((-48, "-2d"), (-24, "-1d"), (0, "now"))


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
    draw_text_bold(
        text_frame,
        text_x,
        text_y,
        next_line if warning_mode else verdict,
        color=text_color,
    )

    draw_text(epd.black_frame, 5, 47, t("label.co2", int(current_ci)))


class GraphAxes:
    """Where a value and an hour index land on the panel.

    Carries the six numbers the plotting used to close over — the value range,
    the box, the point count and the horizontal step — so the helpers below are
    module-level functions instead of definitions nested in `draw_graph`.
    """

    def __init__(self, epd, current_line, week_line):
        screen_w, screen_h = panel_dimensions(epd)
        self.base_x, self.base_y = GRAPH_ORIGIN
        self.width = max(10, screen_w - 10)
        self.height = max(10, min(90, screen_h - self.base_y - 5))
        self.plot_h = max(8, self.height - GRAPH_TICK_BAND)

        # Y-scale from min/max over last week + current timeline values.
        self.values = [
            v for v in current_line + week_line if isinstance(v, (int, float))
        ]
        self.low = min(self.values) if self.values else 0
        self.high = max(self.values) if self.values else 0

        graph_hours = CONFIG.timeline.back_hours_default + CONFIG.timeline.future_hours
        self.npts = min(graph_hours, max(len(current_line), len(week_line)))
        self.step_x = max(1, self.width - 2) / float(max(1, self.npts - 1))

    def norm(self, value):
        if value is None:
            return None
        if self.high == self.low:
            return 0.5
        return (value - self.low) / (self.high - self.low)

    def x_at(self, index):
        return self.base_x + 1 + int(round(index * self.step_x))

    def y_from_norm(self, normalized):
        normalized = min(1.0, max(0.0, normalized))
        return (
            self.base_y + (self.plot_h - 2) - int(round(normalized * (self.plot_h - 3)))
        )


def draw_series(frame, axes, values, dotted=False):
    for index in range(axes.npts - 1):
        a = values[index] if index < len(values) else None
        b = values[index + 1] if index + 1 < len(values) else None
        if a is None or b is None:
            continue
        x1, y1 = axes.x_at(index), axes.y_from_norm(a)
        x2, y2 = axes.x_at(index + 1), axes.y_from_norm(b)
        if not dotted:
            frame.line(x1, y1, x2, y2, EINK_BLACK)
            continue
        dx, dy = x2 - x1, y2 - y1
        steps = max(abs(dx), abs(dy))
        if steps <= 0:
            continue
        for step in range(0, steps + 1, 2):
            px = x1 + (dx * step) // steps
            py = y1 + (dy * step) // steps
            frame.pixel(px, py, EINK_BLACK)


def draw_dashed_hline(epd, x0, x1, y):
    x = int(x0)
    x1 = int(x1)
    y = int(y)
    while x <= x1:
        seg_end = min(x + GRAPH_DASH_LEN - 1, x1)
        seg_w = max(1, seg_end - x + 1)

        epd.black_frame.hline(x, y, seg_w, EINK_WHITE)
        epd.red_frame.hline(x, y, seg_w, EINK_BLACK)
        x = seg_end + GRAPH_DASH_GAP + 1


def value_at_percentile(sorted_values, percentile_value):
    if not sorted_values:
        return None
    percentile_value = min(1.0, max(0.0, float(percentile_value)))
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = percentile_value * (len(sorted_values) - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= len(sorted_values):
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def draw_graph(epd, current_line, week_line):
    if not current_line and not week_line:
        draw_rect(epd.black_frame, 5, 55, 112, 80, color=0, fill=False)
        return

    axes = GraphAxes(epd, current_line, week_line)
    draw_rect(
        epd.black_frame,
        axes.base_x,
        axes.base_y,
        axes.width,
        axes.height,
        color=0,
        fill=False,
    )

    if not axes.values or axes.npts < 2:
        return

    # Current timeline: solid black. Previous-week timeline: dotted black.
    draw_series(epd.black_frame, axes, [axes.norm(v) for v in current_line])
    draw_series(epd.black_frame, axes, [axes.norm(v) for v in week_line], dotted=True)

    # Red dashed threshold bands (percentile cutoffs) across the graph.
    sorted_scale = sorted(axes.values)
    x0 = axes.base_x + 1
    x1 = axes.base_x + axes.width - 2
    for percentile_value in (
        CONFIG.thresholds.green_percentile_max,
        CONFIG.thresholds.yellow_percentile_max,
    ):
        value = value_at_percentile(sorted_scale, percentile_value)
        if value is None:
            continue
        draw_dashed_hline(epd, x0, x1, axes.y_from_norm(axes.norm(value)))

    # "now" marker line
    now_idx = CONFIG.timeline.back_hours_default
    if 0 <= now_idx < axes.npts:
        draw_vline(
            epd.black_frame,
            axes.x_at(now_idx),
            axes.base_y + 1,
            max(1, axes.plot_h - 1),
            color=EINK_BLACK,
        )

    # Day ticks and labels (-48h, -24h, now)
    tick_y0 = axes.base_y + axes.plot_h
    tick_y1 = axes.base_y + axes.height - 2
    for hour_offset, label in GRAPH_DAY_TICKS:
        idx = hour_offset + CONFIG.timeline.back_hours_default
        if idx < 0 or idx >= axes.npts:
            continue
        x = axes.x_at(idx)
        draw_vline(
            epd.black_frame, x, tick_y0, max(1, tick_y1 - tick_y0 + 1), color=EINK_BLACK
        )
        draw_text(
            epd.black_frame,
            max(axes.base_x + 1, x - 8),
            axes.base_y + axes.height - 8,
            label,
            color=EINK_BLACK,
        )
