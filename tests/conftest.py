import importlib.util
import pathlib
import sys
import types
from unittest import mock

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PICO = REPO_ROOT / "pico"


class FakeFrameBuffer:
    """Records how it was built; draws nothing."""

    def __init__(self, buf, width, height, fmt):
        self.buf = buf
        self.width = width
        self.height = height
        self.format = fmt


class FakePin:
    OUT = 1
    IN = 0
    PULL_UP = 2

    def __init__(self, number, mode, pull=None):
        self.number = number
        self.mode = mode
        self.pull = pull
        self._value = 0

    def value(self, value=None):
        # Reads 0 for BUSY, so ReadBusy returns instead of spinning.
        if value is None:
            return self._value
        self._value = value
        return None


class FakeSPI:
    def __init__(self, bus):
        self.bus = bus
        self.writes = []

    def init(self, **_kwargs):
        pass

    def write(self, data):
        self.writes.append(bytes(data))


def micropython_stubs():
    """Just enough of `framebuf`, `machine`, `utime` and `utils` to construct
    the display classes under CPython. Nothing here talks to hardware."""
    framebuf = types.SimpleNamespace(
        FrameBuffer=FakeFrameBuffer,
        MONO_VLSB=0,
        MONO_HLSB=3,
    )
    return {
        "framebuf": framebuf,
        "machine": types.SimpleNamespace(Pin=FakePin, SPI=FakeSPI),
        "utime": types.SimpleNamespace(sleep=lambda _seconds: None),
        "utils": types.SimpleNamespace(log=lambda *_args: None),
    }


@pytest.fixture
def load_firmware():
    """Load one pico/ module by path with the MicroPython stubs in place.

    By path, under a prefixed name, and with the stubs only for the duration
    of the load: putting pico/ on sys.path would let pico/http.py shadow the
    standard library's `http` for the rest of the run.
    """

    def _load(filename):
        name = "pico_" + pathlib.Path(filename).stem
        with mock.patch.dict(sys.modules, micropython_stubs()):
            spec = importlib.util.spec_from_file_location(name, PICO / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    return _load
