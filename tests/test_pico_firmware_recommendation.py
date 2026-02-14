import importlib
import sys
import time
from pathlib import Path

FIRMWARE_SRC = Path(__file__).resolve().parents[1] / "pico" / "firmware"
sys.path.insert(0, str(FIRMWARE_SRC))

fw_recommendation = importlib.import_module("fw_recommendation")


def _point(epoch_hour, value):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_hour))
    return {"datetime": timestamp, "carbonIntensity": value}


def test_recommend_from_week_handles_empty_overlay():
    recommendation = fw_recommendation.recommend_from_week(200, [], lookahead_hours=6)
    assert recommendation["reason"] == "Collecting baseline"


def test_recommend_from_week_returns_run_now_for_low_percentile():
    now = int(time.time())
    history = [_point(now - index * 3600, 200 + (index % 5)) for index in range(30)]
    recommendation = fw_recommendation.recommend_from_week(
        180, history, lookahead_hours=6
    )

    assert recommendation["verdict"] == "RUN NOW"
    assert recommendation["wait_hours"] == 0


def test_recommend_from_week_waits_when_current_is_high():
    now = int(time.time())
    history = []
    for index in range(48):
        value = 120 if index % 4 == 0 else 260
        history.append(_point(now - index * 3600, value))

    recommendation = fw_recommendation.recommend_from_week(
        300, history, lookahead_hours=12
    )

    assert recommendation["verdict"] == "WAIT"
