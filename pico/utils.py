import datetime
import gc
import time
from datetime import timezone

import ujson
import urequests

# Bare-name import, like every other module under pico/. These live in
# textutil so they can be tested under CPython — utils itself cannot be
# imported there — and are re-exported here so no call site has to change.
from textutil import _quote, _to_str, iso_z_to_epoch, urlencode_simple

from config import build_firmware_logger

# Re-exported, not used here: providers import these from utils and there is no
# reason to churn every call site over where the code physically lives.
__all__ = ["_quote", "_to_str", "iso_z_to_epoch", "urlencode_simple"]


def free_mem():
    log("Memory before free: %d KB" % int(gc.mem_free() / 1024))
    gc.collect()
    log("Memory after free: %d KB" % int(gc.mem_free() / 1024))


class ProviderError(RuntimeError):
    pass


def clamp(value, minimum, maximum):
    return minimum if value < minimum else min(value, maximum)


def floor_hour(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def floor_hour_epoch(epoch_seconds):
    return epoch_seconds - (epoch_seconds % 3600)


def epoch_to_iso_z(epoch_seconds):
    year, month, day, hour, minute, second, *_ = time.gmtime(epoch_seconds)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (year, month, day, hour, minute, second)


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def close_response(response):
    if response:
        try:
            response.close()
        except Exception:
            pass


def http_get(url, error_label, headers=None, auth=None):
    response = urequests.get(url, headers=headers, auth=auth)
    if response.status_code != 200:
        close_response(response)
        raise ProviderError("%s HTTP %d" % (error_label, response.status_code))
    return response


def http_get_json(url, error_label, headers=None, auth=None, content_parser=False):
    response = None
    try:
        response = http_get(url, error_label, headers=headers, auth=auth)
        if content_parser:
            payload = ujson.loads(response.content)
        else:
            payload = response.json()
        return payload or {}
    finally:
        close_response(response)


def url_decode(value):
    return (value or "").replace("%20", " ")


def fmt_hhmm_local(epoch_seconds):
    local_time = time.localtime(epoch_seconds)
    return "%02d:%02d" % (local_time[3], local_time[4])


def _format_timestamp(parts, include_seconds=True, separator="T"):
    year, month, day, hour, minute = parts[:5]
    if include_seconds:
        second = parts[5]
        return "%04d-%02d-%02d%s%02d:%02d:%02d" % (
            year,
            month,
            day,
            separator,
            hour,
            minute,
            second,
        )
    return "%04d-%02d-%02d%s%02d:%02d" % (year, month, day, separator, hour, minute)


def _now_stamp():
    return _format_timestamp(time.localtime(), include_seconds=True, separator=" ")


# TODO: _log_rotate(max_files=3)
def log(parts):
    global LOGGER
    LOGGER = build_firmware_logger()
    LOGGER.info(parts)


def percentile(sorted_values, target):
    count = len(sorted_values)
    if count == 0:
        return None
    low, high = 0, count
    while low < high:
        middle = (low + high) >> 1
        if sorted_values[middle] < target:
            low = middle + 1
        else:
            high = middle
    return low / count


def _resolution_to_seconds(resolution_text):
    # Typical: PT60M, PT15M, PT30M, PT1H
    if not resolution_text:
        return 3600
    r = resolution_text.strip()
    if not r.startswith("PT"):
        return 3600
    r = r[2:]
    try:
        if r.endswith("H"):
            return int(r[:-1]) * 3600
        if r.endswith("M"):
            return int(r[:-1]) * 60
    except Exception:
        pass
    return 3600


def iso_utc(dt: datetime.datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TextStream:
    def __init__(self, raw, encoding="utf-8"):
        self.raw = raw
        self.encoding = encoding

    def read(self, n=-1):
        b = self.raw.read(n)
        if b is None:
            return ""
        if isinstance(b, bytes):
            return b.decode(self.encoding, "ignore")
        return b
