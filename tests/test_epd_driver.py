"""The portrait and landscape e-ink drivers differ only where they should.

`EPD_2in13_B_V4_Portrait` was the one display class nothing had ever
constructed. It shares everything with the landscape class except the RAM
data-entry mode and the shape of the two FrameBuffers drawn into, so those are
what this pins: the mode byte the panel receives, that each FrameBuffer's
width, height and bit order describe exactly the bytes behind it, and that
`display()` sends those bytes in the order that layout stores them. A geometry
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


class _PlaneRecorder:
    """Stands in for the send_* methods: the bytes sent after each command."""

    def __init__(self):
        self.planes = {}
        self.events = []
        self._command = None

    def command(self, code):
        self._command = code
        self.planes[code] = bytearray()
        self.events.append(code)

    def turn_on(self):
        self.events.append("refresh")

    def data(self, value):
        self.planes[self._command].append(value)

    def data_block(self, buf):
        self.planes[self._command].extend(buf)


def _planes_sent(panel):
    recorder = _PlaneRecorder()
    panel.send_command = recorder.command
    panel.send_data = recorder.data
    panel.send_data1 = recorder.data_block
    panel.TurnOnDisplay = recorder.turn_on
    panel.display()
    return recorder


def _column_bands(panel, buf):
    # MONO_VLSB: one band of 8 rows per `height` bytes, sent last band first.
    bands, height = panel.width // 8, panel.height
    return bytes(buf[i + j * height] for j in range(bands - 1, -1, -1) for i in range(height))


@pytest.mark.parametrize("cls", ["EPD_2in13_B_V4_Portrait", "EPD_2in13_B_V4_Landscape"])
def test_display_sends_each_plane_in_its_layouts_order(epd, cls):
    panel = getattr(epd, cls)()
    for i in range(len(panel.buffer_black)):
        panel.buffer_black[i] = i % 251
        panel.buffer_red[i] = (i * 7) % 251
    sent = _planes_sent(panel)

    for command, buf in ((0x24, panel.buffer_black), (0x26, panel.buffer_red)):
        expected = bytes(buf) if cls.endswith("Portrait") else _column_bands(panel, buf)
        assert sent.planes[command] == expected
    # Without the refresh after both planes the panel keeps showing the old frame.
    assert sent.events == [0x24, 0x26, "refresh"]
