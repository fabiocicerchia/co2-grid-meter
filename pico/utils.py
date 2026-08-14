import datetime
import gc
import time
from datetime import timezone

import ujson
import urequests

from config import build_firmware_logger


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


# TODO: Use library
def iso_z_to_epoch(iso_timestamp):
    """Convert an ISO-8601 timestamp to epoch seconds.

    Supports:
    - ...Z (UTC)
    - ...+HH:MM / ...-HH:MM offsets

    Notes:
    - Uses time.mktime() which may be local-time based on some MicroPython ports.
      For UTC/Z timestamps on typical Pico builds this is usually acceptable.
    """
    try:
        if not iso_timestamp:
            return None

        s = iso_timestamp.strip()

        # Handle trailing 'Z'
        tz_sign = None
        tz_h = 0
        tz_m = 0

        if s.endswith("Z"):
            s = s[:-1]
        else:
            # Handle timezone offsets like +01:00 or -05:30
            # Find last '+' or '-' after the 'T'
            t_pos = s.find("T")
            if t_pos != -1:
                tail = s[t_pos + 1 :]
                plus = tail.rfind("+")
                minus = tail.rfind("-")
                idx = max(minus, plus)
                if idx != -1:
                    tz_part = tail[idx:]
                    s = s[: t_pos + 1 + idx]
                    tz_sign = tz_part[0]
                    tz_part = tz_part[1:]
                    if len(tz_part) >= 5 and tz_part[2] == ":":
                        tz_h = int(tz_part[0:2])
                        tz_m = int(tz_part[3:5])

        date_part, time_part = s.split("T")
        year, month, day = [int(chunk) for chunk in date_part.split("-")]

        fields = time_part.split(":")
        hour = int(fields[0])
        minute = int(fields[1]) if len(fields) > 1 else 0
        second_text = fields[2] if len(fields) > 2 else "0"
        # Support fractional seconds (e.g. "11:00:00.000Z") from EM payloads.
        dot = second_text.find(".")
        if dot != -1:
            second_text = second_text[:dot]
        second = int(second_text or "0")

        epoch = int(time.mktime((year, month, day, hour, minute, second, 0, 0)))

        if tz_sign:
            offset = tz_h * 3600 + tz_m * 60
            # Local time = UTC + offset for '+', so UTC = local - offset
            epoch = epoch - offset if tz_sign == "+" else epoch + offset

        return epoch
    except Exception:
        return None


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


def _to_str(x):
    if isinstance(x, bytes):
        try:
            return x.decode()
        except Exception:
            return str(x)
    if x is None:
        return ""
    return str(x)


# TODO: Use library
def _quote(s):
    # Minimal percent-encoding suitable for query strings on MicroPython.
    s = _to_str(s)
    return (
        s.replace("%", "%25")
        .replace(" ", "%20")
        .replace("&", "%26")
        .replace("=", "%3D")
        .replace("+", "%2B")
        .replace("?", "%3F")
        .replace("#", "%23")
    )


def urlencode_simple(d):
    # MicroPython-friendly query-string builder; coerces bytes->str.
    parts = []
    for k, v in d.items():
        parts.append("%s=%s" % (_quote(k), _quote(v)))
    return "&".join(parts)


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
