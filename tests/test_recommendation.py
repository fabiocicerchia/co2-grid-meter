from datetime import datetime, timedelta, timezone

from pico.recommendation import compute_recommendation


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
