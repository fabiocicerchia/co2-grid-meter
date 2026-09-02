"""Export shapes for the pull endpoints, with no MicroPython-only imports.

`/em/window` and `/status` exist for the dashboard, which knows the payload it
wants. These two exist for *home automation*, where the client is a Home
Assistant `rest` sensor that should not have to parse a 48-point nested history
to learn one number.

The shaping lives here rather than in `pico/app.py` for the same reason
`textutil.py` and `staticfiles.py` do: app.py pulls in `display`, `fw_network`
and `urequests`, so nothing in it can be exercised under CPython. This module
imports one leaf helper and is otherwise pure, so the CSV quoting and the
truncation rule are covered by the suite.
"""

from textutil import iso_z_to_epoch

# A Pico serves this from tens of KB of heap over a single-connection socket, so
# the response is bounded here rather than by whatever `back_hours` the caller
# asks for. 336 rows is two weeks of hourly data — past any window the firmware
# itself requests, and still under 10 KB of CSV.
EXPORT_MAX_ROWS = 336

CSV_HEADER = "datetime,epoch,carbon_intensity"

# CRLF: RFC 4180 says so, and it is what a spreadsheet opening the file expects.
CSV_EOL = "\r\n"


def _number(value):
    """A carbon-intensity value as CSV text.

    Whole numbers lose the trailing `.0` — most of these values are integers and
    a spreadsheet column reading `430` is friendlier than `430.0`.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number == int(number):
        return str(int(number))
    return str(round(number, 3))


def history_rows(history, max_rows=EXPORT_MAX_ROWS):
    """(iso, epoch, value) for each usable point, newest `max_rows` kept.

    Truncation keeps the *newest* rows. A history longer than the cap means a
    caller asked for more than the device can serialise, and the recent end is
    the half anyone polling for automation actually wants.

    Points with no timestamp or no reading are dropped rather than emitted with
    a hole: a CSV row that is half blank is worse than an absent row, because
    the consumer plots it as a zero.
    """
    rows = []
    for point in history or []:
        iso = point.get("datetime")
        epoch = iso_z_to_epoch(iso) if iso else None
        value = _number(point.get("carbonIntensity"))
        if epoch is None or value == "":
            continue
        rows.append((iso, epoch, value))
    rows.sort(key=lambda row: row[1])
    if max_rows is not None and len(rows) > max_rows:
        rows = rows[-max_rows:]
    return rows


def window_csv(window_json, max_rows=EXPORT_MAX_ROWS):
    """The rolling window as CSV: one documented header row, then the points.

    No field here can contain a comma or a quote — a timestamp, an integer and a
    number — so this does not quote, and `history_rows` guarantees it by
    dropping anything it could not turn into one of those three.
    """
    lines = [CSV_HEADER]
    for iso, epoch, value in history_rows(window_json.get("history"), max_rows):
        lines.append("%s,%d,%s" % (iso, epoch, value))
    return CSV_EOL.join(lines) + CSV_EOL


def summary_from_window(
    window_json,
    current_intensity,
    recommendation,
    now_iso,
    city=None,
    cc=None,
    provider=None,
    uptime_seconds=None,
):
    """One flat object: the current reading, the verdict, and the window's shape.

    Deliberately no `history`. A constrained client polling every few minutes
    should not pay to transfer and parse points it is never going to plot; the
    min/max/count are what a rule branches on, and the full series is one
    request away at `/em/window`.
    """
    values = [float(row[2]) for row in history_rows(window_json.get("history"))]
    recommendation = recommendation or {}
    return {
        "datetime": now_iso,
        "city": city,
        "cc": cc,
        "carbon_intensity": current_intensity,
        "unit": "gCO2eq/kWh",
        # The one field a home-automation rule actually branches on.
        "verdict": recommendation.get("verdict"),
        "reason": recommendation.get("reason"),
        "wait_hours": recommendation.get("wait_hours"),
        "window_points": len(values),
        "window_min": min(values) if values else None,
        "window_max": max(values) if values else None,
        "provider": provider,
        "uptime_seconds": uptime_seconds,
    }
