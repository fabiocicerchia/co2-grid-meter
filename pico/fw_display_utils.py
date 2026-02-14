"""Small display-related helpers shared with firmware."""

from __future__ import annotations

from pico.fw_shared import clamp


def intensity_zone_from_percentile(
    percentile_value, green_percentile_max: float, yellow_percentile_max: float
) -> str:
    if percentile_value is None:
        return "mid"
    if percentile_value <= green_percentile_max:
        return "low"
    if percentile_value <= yellow_percentile_max:
        return "mid"
    return "high"


def led_level_from_percentile(percentile_value, levels: int = 12) -> int:
    if percentile_value is None:
        return 0
    return int(clamp(int(round(percentile_value * levels)), 0, levels))
