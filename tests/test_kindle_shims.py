"""The Kindle stand-ins for framebuf and the e-ink panel.

What goes wrong here goes wrong silently on the device: a sideways or mirrored
picture, red that reads as black, a PNG eips refuses. So the test decodes the
PNG it writes and looks at pixels.
"""

import importlib.util
import pathlib
import struct
import sys
import zlib
from unittest import mock

SHIMS = pathlib.Path(__file__).resolve().parents[1] / "kindle" / "shims"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SHIMS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


framebuf = _load("framebuf")
with mock.patch.dict(sys.modules, {"framebuf": framebuf}):
    epd = _load("epd_driver")


def _decode(path):
    data = pathlib.Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    raw = zlib.decompress(data[idat + 4 : idat + 4 + length])
    stride = width + 1
    return width, height, [raw[y * stride + 1 : (y + 1) * stride] for y in range(height)]


def test_text_draws_the_micropython_glyph():
    fb = framebuf.FrameBuffer(None, 8, 8)
    fb.fill(1)
    fb.text("!", 0, 0, 0)
    # "!" is columns 3 and 4, rows 0-3 and 6: 0x4f.
    assert [fb.pixel(3, y) for y in range(8)] == [0, 0, 0, 0, 1, 1, 0, 1]
    assert fb.pixel(0, 0) == 1


def test_landscape_panel_renders_rotated_scaled_png(tmp_path):
    panel = epd.EPD_2in13_B_V4_Landscape()
    assert (panel.imageblack.width, panel.imageblack.height) == (250, 128)
    panel.imageblack.fill(1)
    panel.imagered.fill(1)
    panel.imageblack.pixel(0, 0, 0)  # top-left: black
    panel.imagered.pixel(249, 0, 0)  # top-right: red

    width, height, rows = _decode(panel.render_png(str(tmp_path / "out.png")))
    assert (width, height) == (epd.SCREEN_W, epd.SCREEN_H)

    # Rotated 90 clockwise: 128x250 at scale 3 is 384x750, centred.
    left, top = (600 - 384) // 2, (800 - 750) // 2
    # The panel's top-left lands top-right; its top-right, bottom-right.
    assert rows[top][left + 383] == epd.BLACK
    assert rows[top + 749][left + 383] == epd.RED
    assert rows[top][left] == epd.WHITE
    assert rows[0][0] == epd.WHITE
