"""Recommendation logic (firmware adapter).

The core decision algorithm lives in :mod:`sim.pico.recommendation`. This module
keeps the firmware API stable while delegating to the shared implementation.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from pico.recommendation import compute_recommendation

from fw_utils import floor_hour_epoch


def recommend_from_week(current_ci, week_history_points, *_, **__):
    """Return a recommendation dict compatible with the firmware endpoints."""

    now_epoch = floor_hour_epoch(int(time.time()))
    now_utc = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    return compute_recommendation(current_ci, week_history_points or [], now_utc)
