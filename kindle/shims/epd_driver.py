"""The Kindle's screen, standing in for pico/epd_driver.py.

Same class names and frame attributes, so pico/display.py cannot tell the
difference. display() turns the two ink planes into an 8-bit grayscale PNG and
hands it to `eips`, the Kindle's own screen tool.

The panel is 250x122, the Kindle 600x800. The picture is scaled by a whole
number, so every 8x8 glyph stays sharp, and turned a quarter so the landscape
layout runs down the long side: stand the Kindle on its side.
"""

import os
import struct
import subprocess
import zlib

import framebuf

EPD_WIDTH = 122
EPD_HEIGHT = 250

# The Kindle 4's screen. Tuning knobs, all overridable from the environment
# (see kindle/extension/bin/start.sh): a different model, or a scale that
# leaves room for something else.
SCREEN_W = int(os.environ.get("CO2_SCREEN_W", "600"))
SCREEN_H = int(os.environ.get("CO2_SCREEN_H", "800"))
SCALE = int(os.environ.get("CO2_SCALE", "3"))
# 90 = clockwise, the panel's top along the Kindle's right edge. 0 or 270.
ROTATE = int(os.environ.get("CO2_ROTATE", "90"))
PNG_PATH = os.environ.get("CO2_PNG", "/tmp/co2meter.png")
# Unset on a desktop, so a render there only writes the PNG.
EIPS = os.environ.get("CO2_EIPS", "eips")

WHITE = 0xFF
BLACK = 0x00
# No red on e-ink: the red plane is drawn as dark grey, dark enough that the
# white text the firmware puts on it (the warning panel) still reads.
RED = 0x55


def _png(width, height, rows):
    """An 8-bit grayscale PNG, stdlib only. `rows` are bytes, one per line."""
    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def compose(black, red):
    """The two planes as one grey per pixel, row by row. Red wins, as on the panel."""
    w, h = black.width, black.height
    out = []
    for y in range(h):
        row = bytearray(w)
        for x in range(w):
            i = y * w + x
            row[x] = RED if red.pixels[i] == 0 else (BLACK if black.pixels[i] == 0 else WHITE)
        out.append(row)
    return out


def rotate(rows, degrees):
    if degrees == 90:
        return [bytearray(col) for col in zip(*rows[::-1])]
    if degrees == 270:
        return [bytearray(col) for col in zip(*rows)][::-1]
    return rows


def place(rows, scale, screen_w, screen_h):
    """Scale by a whole number and centre on a white screen of the given size."""
    h, w = len(rows), len(rows[0])
    sw, sh = w * scale, h * scale
    if sw > screen_w or sh > screen_h:
        raise ValueError("%dx%d at scale %d does not fit %dx%d" % (w, h, scale, screen_w, screen_h))
    left, top = (screen_w - sw) // 2, (screen_h - sh) // 2
    blank = bytes([WHITE]) * screen_w
    out = [blank] * top
    for row in rows:
        line = (
            bytes([WHITE]) * left
            + bytes(v for v in row for _ in range(scale))
            + bytes([WHITE]) * (screen_w - left - sw)
        )
        out.extend([line] * scale)
    out.extend([blank] * (screen_h - top - sh))
    return out


class _KindlePanel:
    def __init__(self, frame_w, frame_h):
        self.width = (EPD_WIDTH // 8) * 8 + 8
        self.height = EPD_HEIGHT
        self.imageblack = framebuf.FrameBuffer(None, frame_w, frame_h)
        self.imagered = framebuf.FrameBuffer(None, frame_w, frame_h)

    def render_png(self, path=PNG_PATH):
        rows = place(rotate(compose(self.imageblack, self.imagered), ROTATE), SCALE, SCREEN_W, SCREEN_H)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(_png(SCREEN_W, SCREEN_H, rows))
        os.replace(tmp, path)
        return path

    def display(self):
        path = self.render_png()
        if EIPS:
            # -f: a full refresh, so the last frame leaves no ghost behind.
            subprocess.call([EIPS, "-f", "-g", path])

    def Clear(self, *_colors):
        self.imageblack.fill(1)
        self.imagered.fill(1)

    def sleep(self):
        pass


class EPD_2in13_B_V4_Landscape(_KindlePanel):
    def __init__(self):
        super().__init__(EPD_HEIGHT, (EPD_WIDTH // 8) * 8 + 8)


class EPD_2in13_B_V4_Portrait(_KindlePanel):
    def __init__(self):
        super().__init__((EPD_WIDTH // 8) * 8 + 8, EPD_HEIGHT)
