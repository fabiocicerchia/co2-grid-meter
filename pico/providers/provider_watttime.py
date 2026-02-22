import time
import ubinascii
import urequests
import gc

from utils import ProviderError, close_response, epoch_to_iso_z, floor_hour_epoch, http_get_json, iso_z_to_epoch, safe_float, urlencode_simple
from config import CONFIG


_watttime_disabled_until = 0


def _watttime_allowed_now():
    return time.time() >= _watttime_disabled_until


def _watttime_disable_for_a_day():
    global _watttime_disabled_until, CONFIG
    _watttime_disabled_until = time.time() + CONFIG.providers.watttime_cooldown_sec


def _basic_auth_header(user, password):
    auth_raw = ("%s:%s" % (user, password)).encode()
    return "Basic " + ubinascii.b2a_base64(auth_raw).strip().decode()


def _watttime_login_token():
    login_url = CONFIG.providers.watttime.base_url + "/login"

    # Preferred style (equivalent to requests + HTTPBasicAuth in CPython).
    try:
        payload = http_get_json(
            login_url,
            "WattTime login",
            auth=(CONFIG.providers.watttime.username, CONFIG.providers.watttime.password),
        )
    except Exception:
        # MicroPython fallback: explicit Authorization header.
        auth = _basic_auth_header(CONFIG.providers.watttime.username, CONFIG.providers.watttime.password)
        if not auth:
            raise ProviderError("Missing ubinascii for Basic auth")
        payload = http_get_json(login_url, "WattTime login", headers={"Authorization": auth})

    token = payload.get("token")
    if not token:
        raise ProviderError("WattTime login missing token")
    # token may be bytes on some MicroPython JSON implementations
    if isinstance(token, bytes):
        token = token.decode()
    elif not isinstance(token, str):
        token = str(token)
    return token


# {'signal_type': 'co2_moer', 'region_full_name': 'Kyrgyzstan', 'region': 'KGZ'}
# TODO: WHY?!
def _watttime_grid_region(lat, lon, token):
    query = urlencode_simple({"latitude": str(lat), "longitude": str(lon), "signal_type": "co2_moer"})
    url = CONFIG.providers.watttime.base_url + "/v3/region-from-loc?" + query
    payload = http_get_json(
        url,
        "WattTime region",
        headers={"Authorization": "Bearer " + token},
    )
    region = payload.get("ba") or payload.get("region")
    if not region:
        raise ProviderError("WattTime region missing ba")
    return region

def parse_watttime_historical_compact(raw, start_epoch, end_epoch):
    """Parse /v3/historical payload with low memory use.

    Avoids response.json() (large nested allocations on Pico) and downsamples
    5-minute points to one average value per hour.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        raw = raw.encode()

    key_ts = b'"point_time":"'
    key_value = b'"value":'

    buckets = {}
    idx = 0
    size = len(raw)
    while idx < size:
        ts_pos = raw.find(key_ts, idx)
        if ts_pos < 0:
            break
        ts_start = ts_pos + len(key_ts)
        ts_end = raw.find(b'"', ts_start)
        if ts_end < 0:
            break

        ts_bytes = raw[ts_start:ts_end]
        value_pos = raw.find(key_value, ts_end)
        if value_pos < 0:
            idx = ts_end + 1
            continue

        value_start = value_pos + len(key_value)
        value_end = value_start
        while value_end < size:
            c = raw[value_end]
            if c in (44, 125):  # ',' or '}'
                break
            value_end += 1

        try:
            ts = ts_bytes.decode()
            epoch = iso_z_to_epoch(ts)
            if epoch is None:
                idx = value_end + 1
                continue
            if epoch < start_epoch or epoch > end_epoch:
                idx = value_end + 1
                continue

            value = safe_float(raw[value_start:value_end].decode())
            if value is None:
                idx = value_end + 1
                continue

            hour = floor_hour_epoch(epoch)
            item = buckets.get(hour)
            if item:
                item[0] += value
                item[1] += 1
            else:
                buckets[hour] = [value, 1]
        except Exception:
            pass

        idx = value_end + 1

    hours = list(buckets.keys())
    hours.sort()
    history = []
    for hour in hours:
        total, count = buckets[hour]
        history.append({"datetime": epoch_to_iso_z(hour), "carbonIntensity": total / count})
    return history



def fetch_watttime_window(lat, lon, start_epoch, end_epoch):
    global CONFIG
    if not (
        CONFIG.providers.watttime.enabled and CONFIG.providers.watttime.username and CONFIG.providers.watttime.password
    ):
        raise ProviderError("WattTime disabled/missing credentials")
    if not _watttime_allowed_now():
        raise ProviderError("WattTime temporarily disabled")

    token = _watttime_login_token()
    region = "CAISO_NORTH" # _watttime_grid_region(lat, lon, token) # TODO: FIX THIS

    response = None
    try:
        query = urlencode_simple({
            "region": region,
            "start": epoch_to_iso_z(start_epoch),
            "end": epoch_to_iso_z(end_epoch),
            "signal_type": "co2_moer",
        })
        url = CONFIG.providers.watttime.base_url + "/v3/historical?" + query
        response = urequests.get(
            url,
            headers={"Authorization": "Bearer " + token},
        )
        if response.status_code == 403:
            _watttime_disable_for_a_day()
            raise ProviderError("WattTime historical forbidden, cooling down")
        if response.status_code != 200:
            raise ProviderError("WattTime historical HTTP %d" % response.status_code)
        raw = response.content
        history = parse_watttime_historical_compact(raw, start_epoch, end_epoch)
        del raw
        gc.collect()

        if not history:
            raise ProviderError("WattTime historical missing data")

        return {"city": region, "history": history, "_provider": "watttime"}
    finally:
        close_response(response)