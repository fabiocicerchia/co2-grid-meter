"""Pure parsing for the Carbon Intensity API v2 (https://ci-api.fabiocicerchia.it).

Deliberately free of MicroPython-only imports so it runs under CPython and can
be unit-tested — the same reason `timeutil.py` lives apart from `utils.py`. The
network wrapper is `providers/ci_api.py`.

v1 is frozen upstream and will be removed. It served one provider data point
(15 minutes wide for ENTSO-E) under a name promising an hour, and no history at
all, which is why the device used to build its own curve by polling. v2 answers
a whole UTC day of hourly means in one document, so the curve comes from the
API and the on-flash sample store is only a cache of days already fetched.
"""

# A day document is columnar: every array is index-aligned to the hour
# beginning `start + i * step_sec`, and a missing hour is null *and present*.
# Dropping the nulls upstream would slide every later value into the wrong
# hour, so they are carried here and skipped by position, never by compaction.

# How old the newest hour may be before the window is refused.
#
# Measured in the wild, not derived from the hourly run: IT on 2026-09-11 was
# generated at 05:21Z with hours through 04:00 and the last one still
# incomplete, so the newest hour is already ~1h20m behind when a run lands and
# ~2h20m behind just before the next one — ENTSO-E publishes late and the day
# document aggregates what has arrived. 65 minutes (the old value) refused
# every healthy window and the device never showed a reading at all.
#
# Four hours tolerates a skipped run without flapping and still catches the
# failure this guards against: a pipeline that stopped, whose newest hour is a
# day old. Calibrate per grid — a faster-publishing country can afford less.
MAX_AGE_SEC = 4 * 3600

HOUR_SEC = 3600
DAY_SEC = 24 * HOUR_SEC

# `consumption_lifecycle` is the figure to report: upstream emissions plus the
# trade adjustment. Zone documents omit both consumption arrays — the import
# adjustment is a national number and does not describe one bidding zone — so
# they fall back to `lifecycle`, and `direct` covers a document with neither.
FIGURES = ("consumption_lifecycle", "lifecycle", "direct")


# "YYYY-MM-DD" — anything else is not a date this API returns.
_ISO_DATE_CHARS = 10


def history_path(country_code, date_str, zone=""):
    """Path for one UTC day (`/v2/IT/history/2026-08-27`, or with a zone
    segment for a bidding zone). An uppercase segment is a code and a
    lowercase one a resource, which is what lets the zone form need no
    `zones/` marker."""
    code = (country_code or "").strip().upper()
    if not code:
        raise ValueError("country code is required")
    date = (date_str or "").strip()
    if len(date) != _ISO_DATE_CHARS:
        raise ValueError("date must be YYYY-MM-DD")
    area = (zone or "").strip().upper()
    if area:
        return "/v2/%s/%s/history/%s" % (code, area, date)
    return "/v2/%s/history/%s" % (code, date)


def day_starts(start_epoch, end_epoch):
    """Midnight UTC of every day the window touches, oldest first.

    Both ends inclusive: a window of `[23:30, 00:30]` needs the day on each
    side of midnight, and asking for one document too few loses an hour of the
    timeline rather than failing loudly.
    """
    first = start_epoch - (start_epoch % DAY_SEC)
    return list(range(first, end_epoch + 1, DAY_SEC))


def day_values(document, figures=FIGURES):
    """First figure array holding a number, as (values, figure_name).

    `basis` is checked even though the history routes are measured-only: an
    annual average is a yearly constant, and a timeline drawn from one is flat,
    so every hour scores alike and the meter recommends "now" forever.

    A `step_sec` other than the documented 3600 is refused rather than adapted
    to. The stored array is hours and nothing downstream carries a step, so
    guessing here would misplace every point in the day.
    """
    if not document or document.get("basis") != "measured":
        return [], None
    if document.get("step_sec") not in (None, HOUR_SEC):
        return [], None
    for name in figures:
        values = document.get(name)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, bool) and isinstance(value, (int, float)):
                return values, name
    return [], None


def hour_points(values, start_epoch):
    """[(hour_epoch, value)] for the hours that have one.

    Index is the hour, so a null is skipped in place and never compacted away.
    """
    if start_epoch is None or not values:
        return []
    points = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        points.append((start_epoch + index * HOUR_SEC, float(value)))
    return points


def stale_error(newest_epoch, now_epoch):
    """None when the newest hour still describes now, else why it does not.

    Only worth asking of a window that ends at the present — the week-shifted
    overlay is seven days old by construction.
    """
    if newest_epoch is None:
        return "no measured hour in the window"
    age = int(now_epoch - newest_epoch)
    if age > MAX_AGE_SEC:
        return "newest reading is %ds old (max %ds)" % (age, MAX_AGE_SEC)
    return None
