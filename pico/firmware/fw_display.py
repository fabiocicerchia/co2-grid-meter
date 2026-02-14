"""E-ink display driver and UI drawing helpers."""

import time

import framebuf
from machine import Pin, SPI

import fw_config
from pico.fw_shared import clamp
from pico.fw_display_utils import intensity_zone_from_percentile as _zone_from_p
from pico.fw_display_utils import led_level_from_percentile as _level_from_p

# E-paper controller register map (Waveshare WS-19588 / IL0373-compatible).
# Using named constants makes the low-level command stream easier to audit.
CMD_SOFT_RESET = 0x12
CMD_DRIVER_OUTPUT_CONTROL = 0x01
CMD_DATA_ENTRY_MODE = 0x11
CMD_RAM_X_WINDOW = 0x44
CMD_RAM_Y_WINDOW = 0x45
CMD_BORDER_WAVEFORM = 0x3C
CMD_RAM_X_POINTER = 0x4E
CMD_RAM_Y_POINTER = 0x4F
CMD_WRITE_BW_RAM = 0x24
CMD_WRITE_RED_RAM = 0x26
CMD_DISPLAY_UPDATE_CONTROL = 0x22
CMD_MASTER_ACTIVATION = 0x20

DATA_GATE_SCAN_NORMAL = 0x00
DATA_XY_INCREMENT = 0x03
DATA_BORDER_LUT = 0x05
DATA_FULL_UPDATE_MODE = 0xF7


class EPDWaveshareWS19588:
    """Waveshare WS-19588 tri-color (B/W/Red) e-paper driver.

    This implementation mirrors the vendor Pico demo command flow so the
    firmware stays wire-compatible with Waveshare's reference init/update
    sequence.
    """

    WIDTH = fw_config.EPD_W
    HEIGHT = fw_config.EPD_H

    def __init__(self):
        self.reset_pin = Pin(fw_config.PIN_RST, Pin.OUT)
        self.busy_pin = Pin(fw_config.PIN_BUSY, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(fw_config.PIN_CS, Pin.OUT)
        self.dc_pin = Pin(fw_config.PIN_DC, Pin.OUT)

        if self.WIDTH % 8 == 0:
            self.width = self.WIDTH
        else:
            self.width = (self.WIDTH // 8) * 8 + 8
        self.height = self.HEIGHT

        self.spi = SPI(fw_config.SPI_BUS)
        self.spi.init(baudrate=4_000_000)

        buffer_size = self.height * self.width // 8
        self.black_buffer = bytearray(buffer_size)
        self.red_buffer = bytearray(buffer_size)
        self.black_frame = framebuf.FrameBuffer(
            self.black_buffer, self.width, self.height, framebuf.MONO_HLSB
        )
        self.red_frame = framebuf.FrameBuffer(
            self.red_buffer, self.width, self.height, framebuf.MONO_HLSB
        )
        self.init()

    def digital_write(self, pin, value):
        pin.value(value)

    def digital_read(self, pin):
        return pin.value()

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

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

    def send_data_buffer(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)

    def wait_until_idle(self):
        while self.digital_read(self.busy_pin) == fw_config.BUSY_ACTIVE:
            self.delay_ms(10)
        self.delay_ms(20)

    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)

    def set_windows(self, x_start, y_start, x_end, y_end):
        self.send_command(CMD_RAM_X_WINDOW)
        self.send_data((x_start >> 3) & 0xFF)
        self.send_data((x_end >> 3) & 0xFF)

        self.send_command(CMD_RAM_Y_WINDOW)
        self.send_data(y_start & 0xFF)
        self.send_data((y_start >> 8) & 0xFF)
        self.send_data(y_end & 0xFF)
        self.send_data((y_end >> 8) & 0xFF)

    def set_cursor(self, x_start, y_start):
        self.send_command(CMD_RAM_X_POINTER)
        self.send_data(x_start & 0xFF)

        self.send_command(CMD_RAM_Y_POINTER)
        self.send_data(y_start & 0xFF)
        self.send_data((y_start >> 8) & 0xFF)

    def init(self):
        self.reset()

        self.wait_until_idle()
        self.send_command(CMD_SOFT_RESET)
        self.wait_until_idle()

        self.send_command(CMD_DRIVER_OUTPUT_CONTROL)
        self.send_data(0xF9)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(CMD_DATA_ENTRY_MODE)
        self.send_data(DATA_XY_INCREMENT)

        self.set_windows(0, 0, self.width - 1, self.height - 1)
        self.set_cursor(0, 0)

        self.send_command(CMD_BORDER_WAVEFORM)
        self.send_data(DATA_BORDER_LUT)

        self.send_command(0x18)
        self.send_data(0x80)

        self.send_command(0x21)
        self.send_data(0x80)
        self.send_data(0x80)

        self.wait_until_idle()

    def clear(self):
        self.black_frame.fill(1)
        self.red_frame.fill(1)

    def display(self):
        self.send_command(CMD_WRITE_BW_RAM)
        self.send_data_buffer(self.black_buffer)

        self.send_command(CMD_WRITE_RED_RAM)
        self.send_data_buffer(self.red_buffer)

        self.send_command(CMD_MASTER_ACTIVATION)
        self.wait_until_idle()


FONT5x8 = {
    " ": [0x00, 0x00, 0x00, 0x00, 0x00],
    "!": [0x00, 0x00, 0x5F, 0x00, 0x00],
    '"': [0x00, 0x07, 0x00, 0x07, 0x00],
    "#": [0x14, 0x7F, 0x14, 0x7F, 0x14],
    "$": [0x24, 0x2A, 0x7F, 0x2A, 0x12],
    "%": [0x23, 0x13, 0x08, 0x64, 0x62],
    "&": [0x36, 0x49, 0x55, 0x22, 0x50],
    "'": [0x00, 0x05, 0x03, 0x00, 0x00],
    "(": [0x00, 0x1C, 0x22, 0x41, 0x00],
    ")": [0x00, 0x41, 0x22, 0x1C, 0x00],
    "*": [0x14, 0x08, 0x3E, 0x08, 0x14],
    "+": [0x08, 0x08, 0x3E, 0x08, 0x08],
    ",": [0x00, 0x50, 0x30, 0x00, 0x00],
    "-": [0x08, 0x08, 0x08, 0x08, 0x08],
    ".": [0x00, 0x60, 0x60, 0x00, 0x00],
    "/": [0x20, 0x10, 0x08, 0x04, 0x02],
    "0": [0x3E, 0x51, 0x49, 0x45, 0x3E],
    "1": [0x00, 0x42, 0x7F, 0x40, 0x00],
    "2": [0x62, 0x51, 0x49, 0x49, 0x46],
    "3": [0x22, 0x41, 0x49, 0x49, 0x36],
    "4": [0x18, 0x14, 0x12, 0x7F, 0x10],
    "5": [0x2F, 0x49, 0x49, 0x49, 0x31],
    "6": [0x3E, 0x49, 0x49, 0x49, 0x32],
    "7": [0x01, 0x71, 0x09, 0x05, 0x03],
    "8": [0x36, 0x49, 0x49, 0x49, 0x36],
    "9": [0x26, 0x49, 0x49, 0x49, 0x3E],
    ":": [0x00, 0x36, 0x36, 0x00, 0x00],
    ";": [0x00, 0x56, 0x36, 0x00, 0x00],
    "<": [0x08, 0x14, 0x22, 0x41, 0x00],
    "=": [0x14, 0x14, 0x14, 0x14, 0x14],
    ">": [0x00, 0x41, 0x22, 0x14, 0x08],
    "?": [0x02, 0x01, 0x59, 0x09, 0x06],
    "@": [0x3E, 0x41, 0x5D, 0x59, 0x4E],
    "A": [0x7E, 0x11, 0x11, 0x11, 0x7E],
    "B": [0x7F, 0x49, 0x49, 0x49, 0x36],
    "C": [0x3E, 0x41, 0x41, 0x41, 0x22],
    "D": [0x7F, 0x41, 0x41, 0x22, 0x1C],
    "E": [0x7F, 0x49, 0x49, 0x49, 0x41],
    "F": [0x7F, 0x09, 0x09, 0x09, 0x01],
    "G": [0x3E, 0x41, 0x49, 0x49, 0x7A],
    "H": [0x7F, 0x08, 0x08, 0x08, 0x7F],
    "I": [0x00, 0x41, 0x7F, 0x41, 0x00],
    "J": [0x20, 0x40, 0x41, 0x3F, 0x01],
    "K": [0x7F, 0x08, 0x14, 0x22, 0x41],
    "L": [0x7F, 0x40, 0x40, 0x40, 0x40],
    "M": [0x7F, 0x02, 0x04, 0x02, 0x7F],
    "N": [0x7F, 0x04, 0x08, 0x10, 0x7F],
    "O": [0x3E, 0x41, 0x41, 0x41, 0x3E],
    "P": [0x7F, 0x09, 0x09, 0x09, 0x06],
    "Q": [0x3E, 0x41, 0x51, 0x21, 0x5E],
    "R": [0x7F, 0x09, 0x19, 0x29, 0x46],
    "S": [0x46, 0x49, 0x49, 0x49, 0x31],
    "T": [0x01, 0x01, 0x7F, 0x01, 0x01],
    "U": [0x3F, 0x40, 0x40, 0x40, 0x3F],
    "V": [0x1F, 0x20, 0x40, 0x20, 0x1F],
    "W": [0x3F, 0x40, 0x38, 0x40, 0x3F],
    "X": [0x63, 0x14, 0x08, 0x14, 0x63],
    "Y": [0x07, 0x08, 0x70, 0x08, 0x07],
    "Z": [0x61, 0x51, 0x49, 0x45, 0x43],
    "[": [0x00, 0x7F, 0x41, 0x41, 0x00],
    "\\": [0x02, 0x04, 0x08, 0x10, 0x20],
    "]": [0x00, 0x41, 0x41, 0x7F, 0x00],
    "^": [0x04, 0x02, 0x01, 0x02, 0x04],
    "_": [0x40, 0x40, 0x40, 0x40, 0x40],
    "`": [0x00, 0x01, 0x02, 0x04, 0x00],
    "a": [0x20, 0x54, 0x54, 0x54, 0x78],
    "b": [0x7F, 0x48, 0x44, 0x44, 0x38],
    "c": [0x38, 0x44, 0x44, 0x44, 0x20],
    "d": [0x38, 0x44, 0x44, 0x48, 0x7F],
    "e": [0x38, 0x54, 0x54, 0x54, 0x18],
    "f": [0x08, 0x7E, 0x09, 0x01, 0x02],
    "g": [0x0C, 0x52, 0x52, 0x52, 0x3E],
    "h": [0x7F, 0x08, 0x04, 0x04, 0x78],
    "i": [0x00, 0x44, 0x7D, 0x40, 0x00],
    "j": [0x20, 0x40, 0x44, 0x3D, 0x00],
    "k": [0x7F, 0x10, 0x28, 0x44, 0x00],
    "l": [0x00, 0x41, 0x7F, 0x40, 0x00],
    "m": [0x7C, 0x04, 0x18, 0x04, 0x78],
    "n": [0x7C, 0x08, 0x04, 0x04, 0x78],
    "o": [0x38, 0x44, 0x44, 0x44, 0x38],
    "p": [0x7C, 0x14, 0x14, 0x14, 0x08],
    "q": [0x08, 0x14, 0x14, 0x18, 0x7C],
    "r": [0x7C, 0x08, 0x04, 0x04, 0x08],
    "s": [0x48, 0x54, 0x54, 0x54, 0x20],
    "t": [0x04, 0x3F, 0x44, 0x40, 0x20],
    "u": [0x3C, 0x40, 0x40, 0x20, 0x7C],
    "v": [0x1C, 0x20, 0x40, 0x20, 0x1C],
    "w": [0x3C, 0x40, 0x30, 0x40, 0x3C],
    "x": [0x44, 0x28, 0x10, 0x28, 0x44],
    "y": [0x0C, 0x50, 0x50, 0x50, 0x3C],
    "z": [0x44, 0x64, 0x54, 0x4C, 0x44],
    "{": [0x00, 0x08, 0x36, 0x41, 0x00],
    "|": [0x00, 0x00, 0x7F, 0x00, 0x00],
    "}": [0x00, 0x41, 0x36, 0x08, 0x00],
    "~": [0x08, 0x08, 0x2A, 0x1C, 0x08],
}


def draw_char(frame, x, y, char, color=0):
    glyph = FONT5x8.get(char)
    if not glyph:
        glyph = FONT5x8.get("?")
    for col, col_data in enumerate(glyph):
        for row in range(8):
            pixel_on = (col_data >> row) & 0x01
            if pixel_on:
                frame.pixel(x + col, y + row, color)


def draw_text(frame, x, y, text, color=0):
    x_pos = x
    for char in text:
        draw_char(frame, x_pos, y, char, color=color)
        x_pos += 6


def draw_rect(frame, x, y, w, h, color=0, fill=False):
    if fill:
        frame.fill_rect(x, y, w, h, color)
        return
    frame.rect(x, y, w, h, color)


def draw_hline(frame, x, y, w, color=0):
    frame.hline(x, y, w, color)


def draw_vline(frame, x, y, h, color=0):
    frame.vline(x, y, h, color)


def draw_leds(epd, zone, level):
    x, y = 5, 5
    led_size = 7
    spacing = 3
    for idx in range(12):
        on = idx < level
        if zone == "low":
            color = 0 if on else 1
            draw_rect(epd.black_frame, x + idx * (led_size + spacing), y, led_size, 5, color, fill=on)
        elif zone == "high":
            color = 0 if on else 1
            draw_rect(epd.red_frame, x + idx * (led_size + spacing), y, led_size, 5, color, fill=on)
        else:
            color = 0 if on else 1
            draw_rect(epd.black_frame, x + idx * (led_size + spacing), y, led_size, 5, color, fill=on)


def draw_wifi_icon(epd, x, y, connected):
    if connected:
        draw_text(epd.black_frame, x, y, "WiFi", color=0)
    else:
        draw_text(epd.red_frame, x, y, "WiFi", color=0)


def draw_time(epd, x, y):
    now = time.localtime()
    time_str = "%02d:%02d" % (now[3], now[4])
    draw_text(epd.black_frame, x, y, time_str, color=0)


def draw_current_panel(epd, current_ci, verdict, next_line):
    draw_text(epd.black_frame, 5, 28, "CO2:", color=0)
    draw_text(epd.black_frame, 45, 28, "%d" % int(current_ci), color=0)
    draw_text(epd.black_frame, 90, 28, "g", color=0)

    draw_rect(epd.black_frame, 5, 40, 112, 40, color=0, fill=False)
    draw_text(epd.black_frame, 10, 46, verdict[:12], color=0)
    if next_line:
        draw_text(epd.black_frame, 10, 58, next_line[:18], color=0)


def _normalize(values):
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [0.5 for _ in values]
    return [(value - minimum) / (maximum - minimum) for value in values]


def draw_graph(epd, past, future):
    past = past[-fw_config.CONFIG.display.graph_points :]
    future = future[: fw_config.CONFIG.display.graph_points]
    values = past + future
    normalized = _normalize(values)

    base_x = 5
    base_y = 95
    width = 112
    height = 80

    draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)

    if not normalized:
        return

    bar_count = len(normalized)
    bar_width = max(1, width // max(1, bar_count))
    for i, value in enumerate(normalized):
        bar_height = int(round(value * (height - 2)))
        x = base_x + 1 + i * bar_width
        y = base_y + height - 1 - bar_height
        if i < len(past):
            draw_rect(epd.black_frame, x, y, bar_width - 1, bar_height, color=0, fill=True)
        else:
            draw_rect(epd.red_frame, x, y, bar_width - 1, bar_height, color=0, fill=True)

    split_x = base_x + 1 + len(past) * bar_width
    draw_vline(epd.black_frame, split_x, base_y, height, color=0)


def intensity_zone_from_percentile(percentile_value):
    return _zone_from_p(
        percentile_value,
        fw_config.CONFIG.thresholds.green_percentile_max,
        fw_config.CONFIG.thresholds.yellow_percentile_max,
    )


def led_level_from_percentile(percentile_value):
    return _level_from_p(percentile_value, levels=12)


# Backwards compatibility name used by fw_app.py
EPD2in13BWR = EPDWaveshareWS19588
