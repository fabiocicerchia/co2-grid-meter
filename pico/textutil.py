"""Text helpers shared by the firmware, with no MicroPython-only imports.

They live apart from `pico/utils.py` for the same reason `pico/timeutil.py`
does: utils imports `urequests`, `ujson` and `config`, so nothing in it can be
exercised under CPython, and these two were the parts most worth testing.

Both were marked `# TODO: Use library`. There is no library to use — a Pico
build ships neither `datetime` nor `urllib.parse` — so the resolution is one
shared, tested implementation rather than a dependency that cannot exist.
"""


def _days_from_civil(year, month, day):
    """Days between 1970-01-01 and the given date, proleptic Gregorian.

    Howard Hinnant's civil-from-days algorithm: shift the year to start in
    March so the leap day lands at the end of it, which removes every special
    case except the 400-year cycle.
    """
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _to_str(x):
    """Bytes or anything else to str, without assuming an encoding is valid.

    Moved here with its two callers rather than left in utils.py, so this
    module has no import back into the MicroPython-only side.
    """
    if isinstance(x, bytes):
        try:
            return x.decode()
        except Exception:
            return str(x)
    if x is None:
        return ""
    return str(x)


def iso_z_to_epoch(iso_timestamp):
    """Convert an ISO-8601 timestamp to epoch seconds.

    Supports:
    - ...Z (UTC)
    - ...+HH:MM / ...-HH:MM offsets

    The conversion is integer arithmetic rather than time.mktime(). mktime
    interprets its tuple in LOCAL time on several MicroPython ports, which
    silently shifted every reading by the device's offset; it also wants a
    9-tuple on CPython and an 8-tuple on MicroPython, so the old call raised
    on CPython and returned None through the except below — which is how this
    went untested for so long. Days-from-civil has neither problem and is
    exact for any date the firmware will ever see.
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

        # Range-checked because the arithmetic below happily accepts month 13.
        # mktime used to reject those; a provider sending a malformed stamp
        # must still read as "no timestamp", not as a date 400 days out.
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
            return None

        epoch = (
            _days_from_civil(year, month, day) * 86400
            + hour * 3600
            + minute * 60
            + second
        )

        if tz_sign:
            offset = tz_h * 3600 + tz_m * 60
            # Local time = UTC + offset for '+', so UTC = local - offset
            epoch = epoch - offset if tz_sign == "+" else epoch + offset

        return epoch
    except Exception:
        return None


def _quote(s):
    """Minimal percent-encoding for query strings.

    Only the characters that would otherwise change the meaning of a query
    string are escaped. Kept exactly as it was when it lived in utils.py: the
    provider URLs in use are built from this, so widening the escape set is a
    behaviour change, not a tidy-up.
    """
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
