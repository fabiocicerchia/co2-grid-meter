
# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
import gc
import io
import time
import xmltok

import urequests as requests

from pico.config import CONFIG
from pico.firmware.fw_utils import ProviderError, _format_timestamp, close_response, epoch_to_iso_z, http_get_json, safe_float


ENTSOE_DOMAIN = {
    # Core ENTSO-E domains + common aliases.
    "AL": "10YAL-KESH-----5",
    "AT": "10YAT-APG------L",
    "BA": "10YBA-JPCC-----D",
    "BE": "10YBE----------2",
    "BG": "10YCA-BULGARIA-R",
    "CH": "10YCH-SWISSGRIDZ",
    "CY": "10YCY-1001A0003J",
    "CZ": "10YCZ-CEPS-----N",
    "DE": "10Y1001A1001A83F",
    "DK": "10Y1001A1001A65H",  # DK1 default
    "DK1": "10YDK-1--------W",
    "DK2": "10YDK-2--------M",
    "EE": "10Y1001A1001A39I",
    "ES": "10YES-REE------0",
    "FI": "10YFI-1--------U",
    "FR": "10YFR-RTE------C",
    "GB": "10YGB----------A",
    "GR": "10YGR-HTSO-----Y",
    "HR": "10YHR-HEP------M",
    "HU": "10YHU-MAVIR----U",
    "IE": "10YIE-1001A00010",
    "IT": "10YIT-GRTN-----B",
    "IT-NORTH": "10Y1001A1001A73I",     # IT1
    "IT-CNORTH": "10Y1001A1001A70O",    # IT2
    "IT-CSOUTH": "10Y1001A1001A71M",    # IT3
    "IT-SOUTH": "10Y1001A1001A788",     # IT4
    "IT-SARDINIA": "10Y1001A1001A74G",  # IT5
    "IT-SICILY": "10Y1001A1001A75E",    # IT6
    "LT": "10YLT-1001A0008Q",
    "LU": "10YLU-CEGEDEL-NQ",
    "LV": "10YLV-1001A00074",
    "ME": "10YCS-CG-TSO---S",
    "MK": "10YMK-MEPSO----8",
    "MT": "10Y1001A1001A93C",
    "NL": "10YNL----------L",
    "NO": "10YNO-0--------C",
    "PL": "10YPL-AREA-----S",
    "PT": "10YPT-REN------W",
    "RO": "10YRO-TEL------P",
    "RS": "10YCS-SERBIATSOV",
    "SE": "10YSE-1--------K",  # SE1 default
    "SE1": "10Y1001A1001A44P",
    "SE2": "10Y1001A1001A45N",
    "SE3": "10Y1001A1001A46L",
    "SE4": "10Y1001A1001A47J",
    "SI": "10YSI-ELES-----O",
    "SK": "10YSK-SEPS-----K",
    "TR": "10YTR-TEIAS----W",
    "UA": "10YUA-WEPS-----0",
    "UK": "10YGB----------A",
}


PSR_EMISSION_FACTOR = {
    "B01": 12,  "B02": 820, "B03": 490, "B04": 780, "B05": 900, "B06": 650,
    "B07": 700, "B08": 950, "B09": 20,  "B10": 12,  "B11": 8,   "B12": 8,
    "B13": 12,  "B14": 15,  "B15": 10,  "B16": 450, "B17": 700, "B18": 12,
    "B19": 10,  "B20": 10,  "B21": 45,
}


def selected_provider(country_code):
    cc = (country_code or "XX").upper()
    entsoe_cc = (CONFIG.providers.entsoe.area_override or cc).upper()

    enabled = []
    if CONFIG.providers.ukci_enabled:
        enabled.append("uk")

    if CONFIG.providers.electricity_maps.enabled and CONFIG.providers.electricity_maps.token:
        enabled.append("em")

    if (
        CONFIG.providers.watttime.enabled
        and CONFIG.providers.watttime.username
        and CONFIG.providers.watttime.password
    ):
        enabled.append("watttime")

    if (
        CONFIG.providers.entsoe.enabled
        and CONFIG.providers.entsoe.token
        and entsoe_cc in ENTSOE_DOMAIN
    ):
        enabled.append("entsoe")

    if len(enabled) > 1:
        raise ProviderError("Enable only one provider at a time: %s" % ",".join(enabled))
    if not enabled:
        raise ProviderError("No providers available")
    return enabled[0]


def ukci_format_timestamp(epoch_value):
    return _format_timestamp(time.gmtime(epoch_value), include_seconds=False) + "Z"


def _parse_provider_history(points, datetime_key, intensity_getter):
    history = []
    for point in points:
        point_time = point.get(datetime_key)
        value = safe_float(intensity_getter(point))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


def parse_ukci_payload(payload):
    return _parse_provider_history(
        payload.get("data") or [],
        datetime_key="from",
        intensity_getter=lambda point: (point.get("intensity") or {}).get("actual") or (point.get("intensity") or {}).get("forecast"),
    )


def parse_em_payload(payload):
    return _parse_provider_history(
        payload.get("history") or payload.get("data") or [],
        datetime_key="datetime",
        intensity_getter=lambda point: point.get("carbonIntensity"),
    )


def fetch_uk_ci_window(start_epoch, end_epoch):
    api_url = "https://api.carbonintensity.org.uk/intensity/%s/%s" % (
        ukci_format_timestamp(start_epoch),
        ukci_format_timestamp(end_epoch),
    )
    payload = http_get_json(api_url, "UKCI")
    return {"city": "Great Britain", "history": parse_ukci_payload(payload), "_provider": "uk"}


def fetch_em_past_range(lat, lon, start_epoch, end_epoch):
    if not (CONFIG.providers.electricity_maps.enabled and CONFIG.providers.electricity_maps.token):
        raise ProviderError("Electricity Maps disabled/missing token")

    query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
        str(lat), str(lon), epoch_to_iso_z(start_epoch), epoch_to_iso_z(end_epoch)
    )
    api_url = CONFIG.providers.electricity_maps.base_url + "/v3/carbon-intensity/past-range?" + query

    payload = http_get_json(
        api_url,
        "EM",
        headers={"auth-token": CONFIG.providers.electricity_maps.token},
        content_parser=True,
    )

    return {
        "city": payload.get("zone") or payload.get("city") or "ElectricityMaps",
        "history": parse_em_payload(payload),
        "_provider": "em",
    }

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
    return (s.replace("%", "%25")
             .replace(" ", "%20")
             .replace("&", "%26")
             .replace("=", "%3D")
             .replace("+", "%2B")
             .replace("?", "%3F")
             .replace("#", "%23"))


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


def entsoe_period_timestamp(epoch_value):
    year, month, day, hour, minute, *_ = time.gmtime(epoch_value)
    return "%04d%02d%02d%02d%02d" % (year, month, day, hour, minute)


def fetch_entsoe_window(country_code, start_epoch, end_epoch):
    if not CONFIG.providers.entsoe.token:
        raise ProviderError("ENTSO-E missing token")

    mapped_country = (CONFIG.providers.entsoe.area_override or country_code).upper()
    if mapped_country not in ENTSOE_DOMAIN:
        raise ProviderError("ENTSO-E country not mapped: %s" % mapped_country)

    params = {
        "securityToken": CONFIG.providers.entsoe.token,
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": ENTSOE_DOMAIN[mapped_country],
        "periodStart": entsoe_period_timestamp(start_epoch),
        "periodEnd": entsoe_period_timestamp(end_epoch),
    }
    url = _to_str(CONFIG.providers.entsoe.base_url) + "?" + urlencode_simple(params)

    buckets = {}
    response = None
    try:
        log("Making request")
        response = requests.get(url)
        log("Provider request made")

        if response.status_code != 200:
            raise ProviderError("ENTSO-E HTTP %d" % response.status_code)

        # Prefer streaming parse to avoid large RAM usage, fall back to StringIO.
        log("Processing data")
        stream = getattr(response, "raw", None)
        if not (stream and hasattr(stream, "read")):
            stream = io.StringIO(_to_str(getattr(response, "text", "") or getattr(response, "content", b"")))

        tok = xmltok.tokenize(TextStream(stream))

        in_timeseries = False
        in_period = False
        in_point = False

        current_tag = None
        psr_code = None
        emission = None

        period_start_epoch = None
        interval_sec = 3600

        point_position = None
        point_quantity = None
        for t in tok:
            event = _to_str(t[0])

            if event == "START_TAG":
                tag = t[1][1] if isinstance(t[1], tuple) else t[1]
                current_tag = tag

                if tag == "TimeSeries":
                    in_timeseries = True
                    psr_code = None
                    emission = None

                elif in_timeseries and tag == "Period":
                    in_period = True
                    period_start_epoch = None
                    interval_sec = 3600

                elif in_period and tag == "Point":
                    in_point = True
                    point_position = None
                    point_quantity = None

            elif event == "TEXT":
                text = _to_str(t[1]).strip()
                if not text or not current_tag:
                    continue

                # ENTSO-E uses <MktPSRType><psrType>Bxx</psrType></MktPSRType>
                if in_timeseries and current_tag == "psrType":
                    psr_code = text
                    emission = PSR_EMISSION_FACTOR.get(psr_code)

                if in_period and current_tag == "start":
                    ts = iso_z_to_epoch(text)
                    if ts is not None:
                        period_start_epoch = ts

                if in_period and current_tag == "resolution":
                    interval_sec = _resolution_to_seconds(text)

                if in_point and current_tag == "position":
                    try:
                        point_position = int(text)
                    except Exception:
                        point_position = None

                if in_point and current_tag == "quantity":
                    try:
                        point_quantity = float(text)
                    except Exception:
                        point_quantity = None

            elif event == "END_TAG":
                tag = t[1][1] if isinstance(t[1], tuple) else t[1]
                current_tag = None

                if tag == "Point" and in_point:
                    if period_start_epoch is not None and point_position and (point_quantity is not None):
                        point_epoch = period_start_epoch + (int(point_position) - 1) * interval_sec
                        hour_epoch = floor_hour_epoch(point_epoch)

                        mw = float(point_quantity)
                        if mw > 0:
                            bucket = buckets.setdefault(hour_epoch, {"mw": 0.0, "weighted": 0.0})
                            bucket["mw"] += mw
                            if emission is not None:
                                bucket["weighted"] += mw * emission
                    in_point = False

                elif tag == "Period" and in_period:
                    in_period = False

                elif tag == "TimeSeries" and in_timeseries:
                    in_timeseries = False
                    psr_code = None
                    emission = None

    finally:
        close_response(response)

    history = []
    for hour_epoch in sorted(buckets.keys()):
        total_mw = buckets[hour_epoch]["mw"]
        if total_mw <= 0:
            continue
        weighted = buckets[hour_epoch]["weighted"]
        # If we couldn't map any fuels (weighted==0), skip rather than return misleading zeros.
        if weighted <= 0:
            continue
        intensity = weighted / total_mw
        history.append({"datetime": epoch_to_iso_z(hour_epoch), "carbonIntensity": int(round(intensity))})

    log("Processing data done")

    return {"city": mapped_country, "history": history, "_provider": "entsoe"}


_watttime_disabled_until = 0


def _watttime_allowed_now():
    return time.time() >= _watttime_disabled_until


def _watttime_disable_for_a_day():
    global _watttime_disabled_until
    _watttime_disabled_until = time.time() + CONFIG.providers.watttime_cooldown_sec


def _basic_auth_header(user, password):
    if not ubinascii:
        return None
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
        response = requests.get(
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


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    provider = selected_provider(country_code)

    if provider == "uk":
        return fetch_uk_ci_window(start_epoch, end_epoch), "uk"
    if provider == "em":
        return fetch_em_past_range(lat, lon, start_epoch, end_epoch), "em"
    if provider == "watttime":
        return fetch_watttime_window(lat, lon, start_epoch, end_epoch), "watttime"
    if provider == "entsoe":
        return fetch_entsoe_window(country_code, start_epoch, end_epoch), "entsoe"

    raise ProviderError("Unknown provider: %s" % provider)

