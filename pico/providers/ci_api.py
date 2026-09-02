"""Carbon Intensity API provider (https://ci-api.fabiocicerchia.it), v2.

Keyless, 213 countries, plus ENTSO-E/EIA/NEM bidding zones where the operator
publishes below national level. v2 serves a whole UTC day of hourly means per
request, so unlike v1 this is a real history provider: the curve comes from the
API instead of being sampled into existence over a week of uptime.

The store on flash is now a cache of day documents, not a measurement record.
A closed day never changes upstream and is fetched once; only today's document
is re-read, because it grows an hour at a time.
"""

import time

from ci_api_parse import (
    day_starts,
    day_values,
    history_path,
    hour_points,
    stale_error,
)
from utils import (
    ProviderError,
    epoch_to_iso_z,
    floor_hour_epoch,
    http_get_json,
    iso_z_to_epoch,
    log,
    utc_offset_now,
)

from config import CONFIG
from providers.base import EmissionsProvider, load_json_store, save_json_store

DAY_SEC = 24 * 3600

# The API answers 1 request per 10s per IP with a 429 beyond that, and asks
# callers to cache what they fetch. One second of margin covers clock slop.
REQUEST_INTERVAL_SEC = 11


def _date_of(epoch):
    return epoch_to_iso_z(epoch)[:10]


def _dates_between(start_epoch, end_epoch):
    """Every UTC date the window touches, oldest first."""
    return [_date_of(day) for day in day_starts(start_epoch, end_epoch)]


def _hours_in_window(days, dates, start_utc, end_utc):
    """The measured hours the window covers, keyed by hour epoch (UTC).

    `hour_points` skips a day's nulls by position; compacting them would slide
    every later value into the wrong hour. See docs/architecture.md.
    """
    by_hour = {}
    for date in dates:
        midnight = iso_z_to_epoch(date + "T00:00:00Z")
        for hour, value in hour_points(days.get(date) or [], midnight):
            if start_utc <= hour <= end_utc:
                by_hour[hour] = value
    return by_hour


class CiApiProvider(EmissionsProvider):
    provider_name = "ci_api"
    store_file = "ci_api_days.json"

    # The overlay reaches nine days back; a fortnight leaves room for a device
    # that was off for a few days without keeping a year of dead weight.
    retention_days = 14

    # Class-level on purpose: fw_providers builds a fresh instance per request,
    # so an instance attribute would forget the last request every time and
    # walk straight into the rate limit.
    _next_request_after = 0

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.ci_api.enabled

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del latitude, longitude

        if not CONFIG.providers.ci_api.enabled:
            raise ProviderError("Carbon Intensity API disabled")

        code = (CONFIG.providers.ci_api.country_override or country_code or "").upper()
        zone = (CONFIG.providers.ci_api.zone or "").upper()
        if not code:
            raise ProviderError("Carbon Intensity API: country code is required")

        # The window arrives on the device's clock, which holds local
        # wall-clock time (see http.set_time); every timestamp in the API is
        # UTC. Mixing the two reads as a two-hour error in summer.
        offset = utc_offset_now()
        now_utc = int(time.time()) - offset
        start_utc = floor_hour_epoch(int(start) - offset)
        end_utc = floor_hour_epoch(int(end) - offset)

        dates = _dates_between(start_utc, end_utc)
        days, added = self._refresh_days(code, zone, dates, _date_of(now_utc))
        if added:
            self._save(code, zone, days, now_utc)

        by_hour = _hours_in_window(days, dates, start_utc, end_utc)
        if not by_hour:
            raise ProviderError(
                "Carbon Intensity API: no measured hours in %s" % (",".join(dates),)
            )
        self._check_freshness(by_hour, end_utc, now_utc)

        history = [
            {
                # Back onto the device's clock: every other timestamp the
                # firmware passes around is local wall-clock labelled Z.
                "datetime": epoch_to_iso_z(hour + offset),
                "carbonIntensity": by_hour[hour],
            }
            for hour in sorted(by_hour)
        ]

        return {
            "city": zone or code,
            "history": history,
            "_provider": self.provider_name,
        }

    def _refresh_days(self, code, zone, dates, today):
        """The cached day documents, refreshed where they can be. `(days, changed)`.

        A closed day never changes upstream and is fetched once; today's grows
        an hour at a time and is re-read. Nothing here is fatal — a day that is
        rate-limited, absent or malformed is skipped, and the window is drawn
        from the days already held.
        """
        days = self._load(code, zone)
        changed = False
        for date in dates:
            if date > today:
                continue  # not written yet; the future is the overlay's job
            if date in days and date != today:
                continue  # a past day never changes again
            values = self._fetch_day(code, zone, date)
            # Compared, not just assigned: today's document is re-read on every
            # refresh and is usually identical, and a flash write every five
            # minutes for nothing is wear for nothing.
            if values is not None and days.get(date) != values:
                days[date] = values
                changed = True
        return days, changed

    def _check_freshness(self, by_hour, end_utc, now_utc):
        """Refuse a present-day window whose newest hour is too old.

        Only a window ending at the present can be stale; the week-shifted
        overlay is seven days old by construction and is exempt.
        """
        if end_utc < floor_hour_epoch(now_utc):
            return
        problem = stale_error(max(by_hour), now_utc)
        if problem:
            raise ProviderError("Carbon Intensity API: %s" % problem)

    def _fetch_day(self, code, zone, date):
        """One day document as its figure's hourly array, or None.

        None is every kind of "not this time" — rate limited, not published,
        malformed. Each is worth another attempt on the next refresh and none
        of them should fail the whole window, which may already hold days
        enough to draw.
        """
        now = int(time.time())
        if now < self._next_request_after:
            return None
        type(self)._next_request_after = now + REQUEST_INTERVAL_SEC

        url = CONFIG.providers.ci_api.base_url.rstrip("/") + history_path(
            code, date, zone
        )
        try:
            document = http_get_json(url, "Carbon Intensity API")
        except Exception as error:
            # 404 is ordinary here: the hourly routes exist only where a
            # provider publishes live generation, and a zone answers only for
            # the runs it appeared in.
            log("Carbon Intensity API: %s unavailable (%s)" % (date, error))
            return None

        values, figure = day_values(document)
        if not values:
            log("Carbon Intensity API: %s has no usable figure" % date)
            return None
        if figure != "consumption_lifecycle":
            # Expected on zone documents, which carry no consumption arrays.
            log("Carbon Intensity API: fell back to %s for %s" % (figure, date))
        return values

    def _store_key(self, code, zone):
        return "%s/%s" % (code, zone) if zone else code

    def _load(self, code, zone):
        store = load_json_store(self.store_file)
        # Cached arrays are one figure for one place. Changing country or zone
        # changes both, so the old days are not comparable and are dropped.
        if store.get("key") != self._store_key(code, zone):
            return {}
        days = store.get("days")
        return days if isinstance(days, dict) else {}

    def _save(self, code, zone, days, now_utc):
        cutoff = _date_of(now_utc - self.retention_days * DAY_SEC)
        kept = {date: values for date, values in days.items() if date >= cutoff}
        save_json_store(
            self.store_file,
            {"key": self._store_key(code, zone), "days": kept},
            self.provider_name,
        )
