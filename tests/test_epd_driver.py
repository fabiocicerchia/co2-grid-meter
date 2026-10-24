"""The portrait and landscape e-ink drivers differ only where they should.

`EPD_2in13_B_V4_Portrait` was the one display class nothing had ever
constructed. It shares everything with the landscape class except the RAM
data-entry mode and the shape of the two FrameBuffers drawn into, so those are
what this pins: the mode byte the panel receives, and that each FrameBuffer's
width, height and bit order describe exactly the bytes behind it. A geometry
that over- or under-runs the buffer is a garbled or clipped frame on the panel.

`framebuf` and `machine` do not exist under CPython; `tests/conftest.py` stubs
them far enough to construct both classes.
"""

import math

import pytest

DATA_ENTRY_MODE = 0x11


@pytest.fixture
def epd(load_firmware):
    return load_firmware("epd_driver.py")


def _bytes_needed(fb, framebuf):
    # MONO_HLSB packs a row into bytes; MONO_VLSB packs a column.
    if fb.format == framebuf.MONO_HLSB:
        return math.ceil(fb.width / 8) * fb.height
    return fb.width * math.ceil(fb.height / 8)


def _data_entry_mode(panel):
    writes = panel.spi.writes
    index = writes.index(bytes([DATA_ENTRY_MODE]))
    return writes[index + 1][0]


def test_portrait_constructs_and_sends_its_own_data_entry_mode(epd):
    portrait = epd.EPD_2in13_B_V4_Portrait()
    landscape = epd.EPD_2in13_B_V4_Landscape()

    assert (portrait.command_code, landscape.command_code) == (0x03, 0x07)
    assert _data_entry_mode(portrait) == 0x03
    assert _data_entry_mode(landscape) == 0x07


def test_framebuffers_are_transposed_between_orientations(epd):
    framebuf = epd.framebuf
    portrait = epd.EPD_2in13_B_V4_Portrait()
    landscape = epd.EPD_2in13_B_V4_Landscape()

    # The panel is 122px wide, padded to the next byte: 128 x 250.
    assert (portrait.width, portrait.height) == (128, 250)
    for fb in (portrait.imageblack, portrait.imagered):
        assert (fb.width, fb.height, fb.format) == (128, 250, framebuf.MONO_HLSB)
    for fb in (landscape.imageblack, landscape.imagered):
        assert (fb.width, fb.height, fb.format) == (250, 128, framebuf.MONO_VLSB)

    assert portrait.imageblack.buf is portrait.buffer_black
    assert portrait.imagered.buf is portrait.buffer_red


@pytest.mark.parametrize("cls", ["EPD_2in13_B_V4_Portrait", "EPD_2in13_B_V4_Landscape"])
def test_framebuffer_geometry_fills_its_buffer_exactly(epd, cls):
    panel = getattr(epd, cls)()
    for fb in (panel.imageblack, panel.imagered):
        assert _bytes_needed(fb, epd.framebuf) == len(fb.buf)


def test_init_sequences_differ_only_in_the_data_entry_mode(epd):
    portrait = epd.EPD_2in13_B_V4_Portrait().spi.writes
    landscape = epd.EPD_2in13_B_V4_Landscape().spi.writes

    assert len(portrait) == len(landscape)
    differing = [i for i, (a, b) in enumerate(zip(portrait, landscape, strict=True)) if a != b]
    assert differing == [portrait.index(bytes([DATA_ENTRY_MODE])) + 1]
