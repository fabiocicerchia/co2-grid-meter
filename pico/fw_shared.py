"""Firmware-compatible shared helpers.

These are pure-Python utilities that are used both by the simulation code and
by the on-device (MicroPython) firmware modules.

They intentionally avoid heavy dependencies (no requests, no dataclasses).
"""

from __future__ import annotations

import time


class ProviderError(RuntimeError):
    """Raised when an emissions provider call fails."""


def clamp(value: float, minimum: float, maximum: float):
    return minimum if value < minimum else maximum if value > maximum else value


def floor_hour_epoch(epoch_seconds: int) -> int:
    return epoch_seconds - (epoch_seconds % 3600)


def epoch_to_iso_z(epoch_seconds: int) -> str:
    year, month, day, hour, minute, second, *_ = time.gmtime(epoch_seconds)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        year,
        month,
        day,
        hour,
        minute,
        second,
    )


def iso_z_to_epoch(iso_timestamp: str):
    """Parse timestamps like 2026-02-16T12:00:00Z to epoch seconds.

    Returns None on parse errors (firmware-friendly).
    """
    try:
        value = iso_timestamp[:-1] if iso_timestamp.endswith("Z") else iso_timestamp
        date_part, time_part = value.split("T")
        year, month, day = [int(chunk) for chunk in date_part.split("-")]
        fields = time_part.split(":")
        hour = int(fields[0])
        minute = int(fields[1]) if len(fields) > 1 else 0
        second = int(fields[2]) if len(fields) > 2 else 0
        # MicroPython's time.mktime expects a tuple of length 8 or 9 depending on port;
        # CPython accepts 9. We keep it short for compatibility.
        return int(time.mktime((year, month, day, hour, minute, second, 0, 0)))
    except Exception:
        return None


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def url_decode(value: str) -> str:
    # Keep this intentionally tiny; firmware only needs spaces for the UI.
    return (value or "").replace("%20", " ")


def fmt_hhmm_local(epoch_seconds: int) -> str:
    local_time = time.localtime(epoch_seconds)
    return "%02d:%02d" % (local_time[3], local_time[4])
