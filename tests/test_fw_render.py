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


@pytest.mark.parametrize("screen_w", [LANDSCAPE_W, PORTRAIT_W])
def test_the_line_ends_inside_the_panel_interior(fw_render, screen_w):
    # n bold glyphs drawn from x=10 end at 10 + 8n; the filled interior of the
    # panel ends at screen_w - 7. One more character would cross it.
    n = fw_render.next_line_chars(screen_w)
    assert 10 + 8 * n <= screen_w - 7 < 10 + 8 * (n + 1)


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
