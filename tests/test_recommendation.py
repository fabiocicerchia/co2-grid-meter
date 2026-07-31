from datetime import datetime, timedelta, timezone

import pytest

# pico/recommendation.py is written for MicroPython's flat, flashed-to-device
# filesystem (see CLAUDE.md): its bare `from config import CONFIG` collides
# with this repo's own top-level config/ package when imported as pico.*
# under pytest, and `pico/utils.py` also needs the MicroPython-only
# urequests/ujson modules. Skip rather than error the whole run until that
# import layout gets a proper CPython-compatible shim.
pico_recommendation = pytest.importorskip("pico.recommendation", exc_type=ImportError)
compute_recommendation = pico_recommendation.compute_recommendation


def _overlay(hours=48, base=200):
    now = datetime.now(timezone.utc) - timedelta(days=7)
    return [
        {
            "datetime": (now + timedelta(hours=index))
            .isoformat()
            .replace("+00:00", "Z"),
            "carbonIntensity": base + (index % 10),
        }
        for index in range(hours)
    ]


def test_compute_recommendation_collecting_baseline():
    result = compute_recommendation(200, _overlay(hours=8), datetime.now(timezone.utc))
    assert result["reason"] == "Collecting baseline"


def test_compute_recommendation_run_now_for_low_percentile():
    now = datetime.now(timezone.utc)
    overlay = _overlay(hours=48, base=300)
    result = compute_recommendation(100, overlay, now)
    assert result["verdict"] == "RUN NOW"


def test_compute_recommendation_wait_for_high_percentile():
    now = datetime.now(timezone.utc)
    overlay = _overlay(hours=48, base=100)
    result = compute_recommendation(1000, overlay, now)
    assert result["verdict"] == "WAIT"
