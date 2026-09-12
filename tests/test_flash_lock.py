"""Flash writes are serialised across the two cores.

The fetcher thread writes its day-document store to flash while the main loop
writes a log line per message. On the RP2 a flash erase parks the other core
with interrupts off, so two cores writing at once hangs the board outright —
no exception, no log line, the e-ink still showing the last frame it drew.

Loaded by path with pico/ on sys.path, like test_ota.py: pico/http.py would
shadow the stdlib `http` package for the rest of the run.
"""

import importlib.util
import pathlib
import sys
import threading

import pytest

PICO = pathlib.Path(__file__).resolve().parents[1] / "pico"


def _load(name, filename):
    sys.path.insert(0, str(PICO))
    try:
        spec = importlib.util.spec_from_file_location(name, PICO / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PICO))


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return _load("pico_config", "config.py")


def _append_from_another_thread(config, message, timeout):
    """True when the append completed inside `timeout`."""
    done = threading.Event()
    threading.Thread(target=lambda: (config.append_log_line(message), done.set()), daemon=True).start()
    return done.wait(timeout)


def test_a_log_line_waits_for_whoever_holds_the_flash_lock(config):
    with config.FLASH_LOCK:
        assert not _append_from_another_thread(config, "second core", 0.2)
    assert _append_from_another_thread(config, "second core", 2)

    day = config._date_from_epoch()
    assert "second core" in pathlib.Path(config.LOG_DIR, day + ".log").read_text()


def test_pruning_runs_once_a_day_not_once_a_line(config, monkeypatch):
    # Listing the directory and stat-ing every file on every message is what
    # made one append a full scan, once a second, forever.
    calls = []
    monkeypatch.setattr(config, "prune_old_logs", lambda **kwargs: calls.append(kwargs))

    for index in range(5):
        config.append_log_line(f"line {index}")
    assert len(calls) == 1

    monkeypatch.setattr(config, "_date_from_epoch", lambda epoch=None: "1999-12-31")
    config.append_log_line("another day")
    assert len(calls) == 2
