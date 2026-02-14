"""Recommendation logic for load shifting."""

from datetime import datetime, timedelta
from pico.utils import percentile

BASELINE_MIN_POINTS = 24
RUN_NOW_THRESHOLD = 0.33
WAIT_THRESHOLD = 0.66
LOOKAHEAD_HOURS = 12


def compute_recommendation(
    current_carbon_intensity, overlay_history, now_utc: datetime
):
    values = _extract_numeric_values(overlay_history)
    if len(values) < BASELINE_MIN_POINTS:
        return {
            "verdict": "OK",
            "reason": "Collecting baseline",
            "next_best": "recheck",
            "wait_hours": None,
        }

    values.sort()
    current_percentile = percentile(values, current_carbon_intensity)
    wait_hours, next_best = _compute_next_best(overlay_history, now_utc)

    if current_percentile <= RUN_NOW_THRESHOLD:
        return {
            "verdict": "RUN NOW",
            "reason": "Cleaner than usual",
            "next_best": "Now",
            "wait_hours": 0,
        }
    if current_percentile <= WAIT_THRESHOLD:
        return {
            "verdict": "OK",
            "reason": "Around average",
            "next_best": next_best,
            "wait_hours": wait_hours or 0,
        }
    return {
        "verdict": "WAIT",
        "reason": "Dirtier than usual",
        "next_best": next_best,
        "wait_hours": wait_hours,
    }


def _compute_next_best(overlay_history, now_utc: datetime):
    week_delta = timedelta(days=7)
    best_slot = None
    horizon = now_utc + timedelta(hours=LOOKAHEAD_HOURS)

    for point in overlay_history:
        point_datetime = point.get("datetime")
        point_carbon_intensity = point.get("carbonIntensity")
        if not point_datetime or not isinstance(point_carbon_intensity, (int, float)):
            continue

        shifted_datetime = (
            datetime.fromisoformat(
                point_datetime.replace("Z", "+00:00")) + week_delta
        )
        if not (now_utc < shifted_datetime <= horizon):
            continue

        if best_slot is None or point_carbon_intensity < best_slot[1]:
            best_slot = (shifted_datetime, point_carbon_intensity)

    if best_slot is None:
        return None, "recheck"

    wait_hours = int(
        round(max(0, (best_slot[0] - now_utc).total_seconds()) / 3600))
    next_best = f"in {wait_hours}h ({best_slot[0].astimezone().strftime('%H:%M')})"
    return wait_hours, next_best


def _extract_numeric_values(overlay_history):
    return [
        float(item.get("carbonIntensity"))
        for item in overlay_history
        if isinstance(item.get("carbonIntensity"), (int, float))
    ]
