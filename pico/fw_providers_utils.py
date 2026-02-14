"""Provider-related helpers shared with firmware."""

from __future__ import annotations

import time

from pico.fw_shared import safe_float


def provider_order(config, country_code: str):
    cc_upper = (country_code or "XX").upper()
    available = []
    if cc_upper == "GB" and getattr(config.providers, "ukci_enabled", False):
        available.append("uk")

    em = getattr(config.providers, "electricity_maps", None)
    if em and getattr(em, "enabled", False) and getattr(em, "token", None):
        available.append("em")

    wt = getattr(config.providers, "watttime", None)
    if (
        wt
        and getattr(wt, "enabled", False)
        and getattr(wt, "username", None)
        and getattr(wt, "password", None)
    ):
        available.append("watttime")

    return available


def ukci_format_timestamp(epoch_value: int) -> str:
    year, month, day, hour, minute, *_ = time.gmtime(epoch_value)
    return "%04d-%02d-%02dT%02d:%02dZ" % (year, month, day, hour, minute)


def parse_ukci_payload(payload: dict):
    history = []
    for point in payload.get("data") or []:
        point_time = point.get("from")
        point_intensity = (point.get("intensity") or {}).get("actual") or (
            point.get("intensity") or {}
        ).get("forecast")
        value = safe_float(point_intensity)
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda point: point["datetime"])
    return history


def parse_em_payload(payload: dict):
    history = []
    points = payload.get("history") or payload.get("data") or []
    for point in points:
        point_time = point.get("datetime")
        value = safe_float(point.get("carbonIntensity"))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda point: point["datetime"])
    return history
