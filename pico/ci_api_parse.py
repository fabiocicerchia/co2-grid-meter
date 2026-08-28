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

# The measured pipeline runs hourly; more than 65 minutes without a new hour
# means a run was missed and the newest value no longer describes now.
MAX_AGE_SEC = 3900

HOUR_SEC = 3600
DAY_SEC = 24 * HOUR_SEC

# `consumption_lifecycle` is the figure to report: upstream emissions plus the
# trade adjustment. Zone documents omit both consumption arrays — the import
# adjustment is a national number and does not describe one bidding zone — so
# they fall back to `lifecycle`, and `direct` covers a document with neither.
FIGURES = ("consumption_lifecycle", "lifecycle", "direct")


def history_path(country_code, date_str, zone=""):
    """Path for one UTC day (`/v2/IT/history/2026-08-27`, or with a zone
    segment for a bidding zone). An uppercase segment is a code and a
    lowercase one a resource, which is what lets the zone form need no
    `zones/` marker."""
    code = (country_code or "").strip().upper()
    if not code:
        raise ValueError("country code is required")
    date = (date_str or "").strip()
    if len(date) != 10:
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
    days = []
    day = start_epoch - (start_epoch % DAY_SEC)
    while day <= end_epoch:
        days.append(day)
        day += DAY_SEC
    return days


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
