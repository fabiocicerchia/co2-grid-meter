"""Pure parsing for the Carbon Intensity API (https://ci-api.fabiocicerchia.it).

Deliberately free of MicroPython-only imports so it runs under CPython and can
be unit-tested — the same reason `timeutil.py` lives apart from `utils.py`. The
network wrapper is `providers/ci_api.py`.
"""

# The API serves static objects straight from a bucket, so nothing evaluates
# freshness at request time and there is no `stale` flag to read. The pipeline
# behind it runs hourly; more than 65 minutes means a run was missed.
MAX_AGE_SEC = 3900

# `consumption_lifecycle` is the figure to report: upstream emissions plus the
# trade adjustment. Zone readings omit both consumption figures — the import
# adjustment is a national number and does not describe one bidding zone — so
# they fall back to `lifecycle`, and `direct` covers a payload with neither.
FIGURES = ("consumption_lifecycle", "lifecycle", "direct")


def reading_path(country_code, zone=""):
    """Path for a country (`/v1/last-hour/IT`) or a zone (`/v1/zones/IT/SICI`)."""
    code = (country_code or "").strip().upper()
    if not code:
        raise ValueError("country code is required")
    area = (zone or "").strip().upper()
    if area:
        return "/v1/zones/%s/%s" % (code, area)
    return "/v1/last-hour/%s" % code


def pick_intensity(payload, figures=FIGURES):
    """First figure present, in preference order, as (value, figure_name)."""
    for name in figures:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        return float(value), name
    return None, None


def freshness_error(payload, generated_at_epoch, now_epoch):
    """None when the reading is a fresh measurement, else why it is unusable.

    Two distinct failures, and the first is the one that bites. A payload with
    `basis == "annual-average"` is a yearly constant wearing an hourly
    reading's shape: store it as a sample and the timeline is a flat line, so
    every hour scores identically and the meter recommends "now" forever. A
    `measured` reading that is merely old means the hourly pipeline missed a
    run, and the value no longer describes the hour we are asking about.
    """
    basis = payload.get("basis")
    if basis != "measured":
        return "basis is %s, not a measurement" % (basis,)
    if generated_at_epoch is None:
        return "generated_at missing or unparsable"
    age = int(now_epoch - generated_at_epoch)
    if age > MAX_AGE_SEC:
        return "reading is %ds old (max %ds)" % (age, MAX_AGE_SEC)
    return None
