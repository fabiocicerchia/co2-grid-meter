"""The recommendation line fits the panel it is drawn on, in either orientation.

`make_next_line` cut the reason to a fixed 22 characters: seven short of what
fits in landscape, and nine more than fits in portrait, where framebuf then
clipped it silently. The wait branch was not cut at all. The limit is now
derived from the panel width and both branches obey it.

`pico/fw_render.py` imports the display stack, so its MicroPython-facing
neighbours are stubbed for the duration of the load; `i18n`, `textutil` and
`timeutil` are the real, import-free modules.
"""

import importlib.util
import pathlib
import sys
from unittest import mock

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"

LANDSCAPE_W = 250
PORTRAIT_W = 128
LONG_REASON = "Grid is much dirtier than usual for this hour"


def _load(name, filename, stubs=None):
    with mock.patch.dict(sys.modules, stubs or {}):
        spec = importlib.util.spec_from_file_location(name, PICO / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def fw_render():
    utils = mock.MagicMock()
    utils.fmt_hhmm_local.return_value = "14:00"
    stubs = {
        "app": mock.MagicMock(),
        "display": mock.MagicMock(),
        "fw_graph": mock.MagicMock(),
        "fw_network": mock.MagicMock(),
        "utils": utils,
        "config": mock.MagicMock(),
        "i18n": _load("i18n", "i18n.py"),
        "textutil": _load("textutil", "textutil.py"),
        "timeutil": _load("timeutil", "timeutil.py"),
    }
    return _load("pico_fw_render", "fw_render.py", stubs)


def test_the_limit_is_derived_from_the_panel_width(fw_render):
    assert fw_render.next_line_chars(LANDSCAPE_W) == 29
    assert fw_render.next_line_chars(PORTRAIT_W) == 13


class _Frame:
    """Records the panel's filled rectangles and the text drawn on it."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rects = []
        self.texts = []

    def fill_rect(self, x, y, w, h, _color):
        self.rects.append((x, y, w, h))

    def text(self, text, x, y, _color):
        self.texts.append((text, x, y))


@pytest.fixture
def display():
    i18n = _load("i18n", "i18n.py")
    stubs = {
        "epd_driver": mock.MagicMock(),
        "utils": mock.MagicMock(),
        "config": mock.MagicMock(),
        "i18n": i18n,
    }
    return _load("pico_display", "display.py", stubs)


@pytest.mark.parametrize("screen_w", [LANDSCAPE_W, PORTRAIT_W])
def test_the_line_ends_inside_the_panel_interior(fw_render, display, screen_w):
    # Measured against display.draw_current_panel itself, so a change to the
    # panel's geometry there fails here instead of clipping on the device.
    n = fw_render.next_line_chars(screen_w)
    epd = mock.Mock(black_frame=_Frame(screen_w, 122), red_frame=_Frame(screen_w, 122))

    display.draw_current_panel(epd, 300, "WAIT", "x" * n)

    interior_x, _, interior_w, _ = epd.red_frame.rects[-1]
    drawn = [(x, len(text)) for text, x, _ in epd.red_frame.texts if text == "x" * n]
    right_edge = max(x + 8 * length for x, length in drawn)  # 8px glyphs
    assert right_edge <= interior_x + interior_w
    assert right_edge + 8 > interior_x + interior_w  # one more would not fit


@pytest.mark.parametrize(
    ("screen_w", "expected"),
    [
        (LANDSCAPE_W, "Grid is much dirtier than"),
        (PORTRAIT_W, "Grid is much"),
    ],
    ids=["landscape", "portrait"],
)
def test_a_long_reason_is_cut_between_words_to_fit(fw_render, screen_w, expected):
    limit = fw_render.next_line_chars(screen_w)
    line = fw_render.make_next_line({"reason": LONG_REASON}, limit)

    assert line == expected
    assert len(line) <= limit


@pytest.mark.parametrize(
    ("screen_w", "expected"),
    [
        (LANDSCAPE_W, "WAIT 3h (14:00)"),
        (PORTRAIT_W, "WAIT 3h"),
    ],
    ids=["landscape", "portrait"],
)
def test_the_wait_line_obeys_the_same_limit(fw_render, screen_w, expected):
    limit = fw_render.next_line_chars(screen_w)
    line = fw_render.make_next_line({"wait_hours": 3, "reason": LONG_REASON}, limit)

    assert line == expected
    assert len(line) <= limit


def test_a_short_reason_is_untouched_and_a_missing_one_is_empty(fw_render):
    assert fw_render.make_next_line({"reason": "  Cleaner  "}, 13) == "Cleaner"
    assert fw_render.make_next_line({}, 13) == ""


@pytest.mark.parametrize(
    ("screen_w", "expected"),
    [
        (LANDSCAPE_W, "Grid is much dirtier than"),
        (PORTRAIT_W, "Grid is much"),
    ],
    ids=["landscape", "portrait"],
)
def test_render_screen_fits_the_line_to_the_panel_it_draws_on(fw_render, screen_w, expected):
    fw_render.CONFIG.display.render_min_interval_sec = 0
    fw_render.panel_dimensions.return_value = (screen_w, None)  # height is unused here
    fw_render.aligned_lines = lambda *_args: ([], [], [])

    fw_render.render_screen({"recommendation": {"verdict": "WAIT", "reason": LONG_REASON}}, {}, {})

    assert fw_render.draw_current_panel.call_args.args[3] == expected
