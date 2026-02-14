"""Single-file Pico firmware bundle.

This file is provided so you can copy/paste one script to the device.
It inlines the behavior from the `pico/firmware/*` modules and keeps the
same HTTP API:
- GET /status
- GET /em/window
- GET /em/window-overlay
"""

# =========================
# Runtime imports / fallbacks
# =========================

import gc
import socket
import time

try:
    import network
except Exception:  # pragma: no cover
    network = None

try:
    import framebuf
    from machine import Pin, SPI
except Exception:  # pragma: no cover
    framebuf = None
    Pin = SPI = None

try:
    import urequests as requests
except Exception:  # pragma: no cover
    requests = None

try:
    import ubinascii
except Exception:  # pragma: no cover
    ubinascii = None

try:
    import xmltok
except Exception:  # pragma: no cover
    xmltok = None

try:
    import xml.etree.ElementTree as _xml_etree
except Exception:  # pragma: no cover
    try:
        import uxml as _xml_etree
    except Exception:  # pragma: no cover
        _xml_etree = None


# =========================
# Config
# =========================

try:
    import os
except Exception:  # pragma: no cover
    os = None

try:
    import uos
except Exception:  # pragma: no cover
    uos = None


def _env(name, default):
    for module in (os, uos):
        if not module:
            continue
        getenv = getattr(module, "getenv", None)
        if callable(getenv):
            value = getenv(name)
            return default if value is None else value

        environ = getattr(module, "environ", None)
        if isinstance(environ, dict) and name in environ:
            return environ[name]
    return default


class CONFIG:
    class wifi:
        ssid = _env("WIFI_SSID", "YOUR_WIFI_SSID")
        password = _env("WIFI_PASS", "YOUR_WIFI_PASSWORD")

    class defaults:
        latitude = float(_env("DEFAULT_LAT", "41.9028"))
        longitude = float(_env("DEFAULT_LON", "12.4964"))
        city = _env("DEFAULT_CITY", "Rome")
        country = _env("DEFAULT_CC", "IT")

    class providers:
        ukci_enabled = _env("UKCI_ENABLED", "1") == "1"

        class electricity_maps:
            enabled = _env("EM_ENABLED", "0") == "1"
            token = _env("EM_TOKEN", "")
            base_url = _env("EM_BASE", "https://api.electricitymaps.org")

        class watttime:
            enabled = _env("WT_ENABLED", "1") == "1"
            username = _env("WATTTIME_USERNAME", "")
            password = _env("WATTTIME_PASSWORD", "")
            base_url = _env("WT_BASE", "https://api.watttime.org")

        class entsoe:
            token = _env("ENTSOE_TOKEN", "")
            base_url = _env("ENTSOE_BASE", "https://web-api.tp.entsoe.eu/api")
            area_override = _env("ENTSOE_AREA", "")

        watttime_cooldown_sec = int(_env("WT_COOLDOWN_SEC", str(24 * 3600)))

    class timeline:
        back_hours_default = int(_env("BACK_HOURS_DEFAULT", "48"))
        past_hours = int(_env("PAST_HOURS", "36"))
        future_hours = int(_env("FUTURE_HOURS", "12"))
        lookahead_hours = int(_env("LOOKAHEAD_HOURS", "12"))

    class thresholds:
        green_percentile_max = float(_env("P_GREEN_MAX", "0.33"))
        yellow_percentile_max = float(_env("P_YELLOW_MAX", "0.66"))

    class server:
        host = _env("HOST", "0.0.0.0")
        port = int(_env("PICO_PORT", "8080"))

    class display:
        render_min_interval_sec = int(_env("RENDER_MIN_INTERVAL_SEC", "60"))

    cache_refresh_seconds = int(_env("PICO_CACHE_REFRESH_SECONDS", "3600"))


EPD_W = 122
EPD_H = 250
SPI_BUS = 1
PIN_CS = 9
PIN_DC = 8
PIN_RST = 12
PIN_BUSY = 13
BUSY_ACTIVE = 1


# =========================
# Shared utils
# =========================


class ProviderError(RuntimeError):
    pass


def clamp(value, minimum, maximum):
    return minimum if value < minimum else maximum if value > maximum else value


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


def url_decode(value):
    return (value or "").replace("%20", " ")


def fmt_hhmm_local(epoch_seconds):
    local_time = time.localtime(epoch_seconds)
    return "%02d:%02d" % (local_time[3], local_time[4])


def iso_z_to_epoch(iso_timestamp):
    try:
        value = iso_timestamp[:-1] if iso_timestamp.endswith("Z") else iso_timestamp
        date_part, time_part = value.split("T")
        year, month, day = [int(chunk) for chunk in date_part.split("-")]
        fields = time_part.split(":")
        hour = int(fields[0])
        minute = int(fields[1]) if len(fields) > 1 else 0
        second = int(fields[2]) if len(fields) > 2 else 0
        return int(time.mktime((year, month, day, hour, minute, second, 0, 0)))
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


class TtlCache:
    def __init__(self, ttl_seconds):
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._store = {}

    def get(self, key):
        now = time.time()
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= now:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value):
        self._store[key] = (time.time() + self.ttl_seconds, value)
        return value

    def get_or_set(self, key, factory):
        value = self.get(key)
        if value is not None:
            return value
        return self.set(key, factory())


# =========================
# Recommendation
# =========================


def compute_recommendation(current_carbon_intensity, overlay_history, now_epoch):
    values = [
        float(item.get("carbonIntensity"))
        for item in overlay_history
        if isinstance(item.get("carbonIntensity"), (int, float))
    ]
    if len(values) < 24:
        return {
            "verdict": "OK",
            "reason": "Collecting baseline",
            "next_best": "recheck",
            "wait_hours": None,
        }

    values.sort()
    current_percentile = percentile(values, current_carbon_intensity)
    wait_hours, next_best = _compute_next_best(overlay_history, now_epoch)

    if current_percentile <= 0.33:
        return {"verdict": "RUN NOW", "reason": "Cleaner than usual", "next_best": "Now", "wait_hours": 0}
    if current_percentile <= 0.66:
        return {"verdict": "OK", "reason": "Around average", "next_best": next_best, "wait_hours": wait_hours or 0}
    return {"verdict": "WAIT", "reason": "Dirtier than usual", "next_best": next_best, "wait_hours": wait_hours}


def _compute_next_best(overlay_history, now_epoch):
    best = None
    horizon_epoch = now_epoch + (12 * 3600)

    for point in overlay_history:
        ts = point.get("datetime")
        ci = point.get("carbonIntensity")
        if not ts or not isinstance(ci, (int, float)):
            continue

        point_epoch = iso_z_to_epoch(ts)
        if point_epoch is None:
            continue

        shifted_epoch = point_epoch + (7 * 24 * 3600)
        if not (now_epoch < shifted_epoch <= horizon_epoch):
            continue

        if best is None or ci < best[1]:
            best = (shifted_epoch, ci)

    if best is None:
        return None, "recheck"

    wait_hours = int(round(max(0, (best[0] - now_epoch)) / 3600))
    return wait_hours, "in %dh (%s)" % (wait_hours, fmt_hhmm_local(best[0]))


def recommend_from_week(current_ci, week_history_points, *_, **__):
    now_epoch = floor_hour_epoch(int(time.time()))
    return compute_recommendation(current_ci, week_history_points or [], now_epoch)


# =========================
# Provider helpers + providers
# =========================



ENTSOE_DOMAIN = {
    "IT": "10YIT-GRTN-----B",
    "FR": "10YFR-RTE------C",
    "DE": "10Y1001A1001A83F",
    "ES": "10YES-REE------0",
    "PT": "10YPT-REN------W",
    "NL": "10YNL----------L",
    "BE": "10YBE----------2",
    "CH": "10YCH-SWISSGRIDZ",
    "AT": "10YAT-APG------L",
    "IE": "10YIE-1001A00010",
    "GB": "10YGB----------A",
    "UK": "10YGB----------A",
}

PSR_EMISSION_FACTOR = {
    "B01": 12, "B02": 820, "B03": 490, "B04": 780, "B05": 900, "B06": 650,
    "B07": 700, "B08": 950, "B09": 20, "B10": 12, "B11": 8, "B12": 8,
    "B13": 12, "B14": 15, "B15": 10, "B16": 450, "B17": 700, "B18": 12,
    "B19": 10, "B20": 10, "B21": 45,
}

def provider_order(country_code):
    cc = (country_code or "XX").upper()
    available = []
    if cc in ("GB", "UK") and CONFIG.providers.ukci_enabled:
        available.append("uk")
    if (
        CONFIG.providers.watttime.enabled
        and CONFIG.providers.watttime.username
        and CONFIG.providers.watttime.password
    ):
        available.append("watttime")

    entsoe_cc = (CONFIG.providers.entsoe.area_override or cc).upper()
    if CONFIG.providers.entsoe.token and entsoe_cc in ENTSOE_DOMAIN:
        available.append("entsoe")

    if CONFIG.providers.electricity_maps.enabled and CONFIG.providers.electricity_maps.token:
        available.append("em")
    return available


def ukci_format_timestamp(epoch_value):
    year, month, day, hour, minute, *_ = time.gmtime(epoch_value)
    return "%04d-%02d-%02dT%02d:%02dZ" % (year, month, day, hour, minute)


def parse_ukci_payload(payload):
    history = []
    for point in payload.get("data") or []:
        point_time = point.get("from")
        intensity = (point.get("intensity") or {}).get("actual") or (point.get("intensity") or {}).get("forecast")
        value = safe_float(intensity)
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


def parse_em_payload(payload):
    history = []
    for point in payload.get("history") or payload.get("data") or []:
        point_time = point.get("datetime")
        value = safe_float(point.get("carbonIntensity"))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


def fetch_uk_ci_window(start_epoch, end_epoch):
    if not requests:
        raise ProviderError("urequests not available")
    api_url = "https://api.carbonintensity.org.uk/intensity/%s/%s" % (
        ukci_format_timestamp(start_epoch),
        ukci_format_timestamp(end_epoch),
    )
    response = None
    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            raise ProviderError("UKCI HTTP %d" % response.status_code)
        payload = response.json()
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass
    return {"city": "Great Britain", "history": parse_ukci_payload(payload), "_provider": "uk"}


def fetch_em_past_range(lat, lon, start_epoch, end_epoch):
    if not requests:
        raise ProviderError("urequests not available")
    if not (CONFIG.providers.electricity_maps.enabled and CONFIG.providers.electricity_maps.token):
        raise ProviderError("Electricity Maps disabled/missing token")

    query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
        str(lat), str(lon), epoch_to_iso_z(start_epoch), epoch_to_iso_z(end_epoch)
    )
    api_url = CONFIG.providers.electricity_maps.base_url + "/v3/carbon-intensity/past-range?" + query

    response = None
    try:
        response = requests.get(api_url, headers={"auth-token": CONFIG.providers.electricity_maps.token})
        if response.status_code != 200:
            raise ProviderError("EM HTTP %d" % response.status_code)
        payload = response.json()
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass

    return {
        "city": payload.get("zone") or payload.get("city") or "ElectricityMaps",
        "history": parse_em_payload(payload),
        "_provider": "em",
    }


def _parse_xml_root(xml_text):
    """Parse ENTSO-E XML with xmltok-first strategy.

    We prefer `xmltok` when available. If the installed xmltok variant does not
    expose a tree parser API, we fallback to ElementTree/uxml.
    """

    if xmltok:
        fromstring = getattr(xmltok, "fromstring", None)
        if callable(fromstring):
            return fromstring(xml_text)

        parse = getattr(xmltok, "parse", None)
        if callable(parse):
            return parse(xml_text)

    if _xml_etree:
        return _xml_etree.fromstring(xml_text)

    raise ProviderError("XML parser not available (xmltok/ElementTree missing)")


def _strip_xml_namespaces(root):
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]


def _safe_xml_text(element, path, default=""):
    child = element.find(path)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _resolution_to_seconds(resolution):
    return 3600 if resolution == "PT60M" else 900


def _extract_hourly_buckets(root):
    buckets = {}
    for series in root.findall(".//TimeSeries"):
        psr_type = series.find(".//MktPSRType/psrType")
        emission = PSR_EMISSION_FACTOR.get(psr_type.text.strip() if psr_type is not None and psr_type.text else None)

        period = series.find(".//Period")
        if period is None:
            continue

        period_start_text = _safe_xml_text(period, "timeInterval/start")
        resolution = _safe_xml_text(period, "resolution")
        if not period_start_text:
            continue

        period_start_epoch = iso_z_to_epoch(period_start_text)
        if period_start_epoch is None:
            continue

        interval_sec = _resolution_to_seconds(resolution)

        for point in period.findall("Point"):
            position = int(_safe_xml_text(point, "position", "0") or "0")
            quantity_mw = float(_safe_xml_text(point, "quantity", "0") or "0")
            hour_epoch = floor_hour_epoch(period_start_epoch + (position - 1) * interval_sec)
            bucket = buckets.setdefault(hour_epoch, {"mw": 0.0, "weighted": 0.0})
            bucket["mw"] += quantity_mw
            if emission is not None:
                bucket["weighted"] += quantity_mw * emission
    return buckets


def fetch_entsoe_window(country_code, start_epoch, end_epoch):
    if not requests:
        raise ProviderError("urequests not available")
    if not CONFIG.providers.entsoe.token:
        raise ProviderError("ENTSO-E missing token")

    mapped_country = (CONFIG.providers.entsoe.area_override or country_code).upper()
    if mapped_country not in ENTSOE_DOMAIN:
        raise ProviderError("ENTSO-E country not mapped: %s" % mapped_country)

    response = None
    try:
        response = requests.get(
            CONFIG.providers.entsoe.base_url,
            params={
                "securityToken": CONFIG.providers.entsoe.token,
                "documentType": "A75",
                "processType": "A16",
                "in_Domain": ENTSOE_DOMAIN[mapped_country],
                "periodStart": time.strftime("%Y%m%d%H%M", time.gmtime(start_epoch)),
                "periodEnd": time.strftime("%Y%m%d%H%M", time.gmtime(end_epoch)),
            },
        )
        if response.status_code != 200:
            raise ProviderError("ENTSO-E HTTP %d" % response.status_code)
        root = _parse_xml_root(response.text)
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass

    _strip_xml_namespaces(root)
    buckets = _extract_hourly_buckets(root)

    history = []
    for hour_epoch in sorted(buckets.keys()):
        total_mw = buckets[hour_epoch]["mw"]
        if total_mw <= 0:
            continue
        intensity = buckets[hour_epoch]["weighted"] / total_mw
        history.append({"datetime": epoch_to_iso_z(hour_epoch), "carbonIntensity": int(round(intensity))})

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
    if not requests:
        raise ProviderError("urequests not available")
    auth = _basic_auth_header(CONFIG.providers.watttime.username, CONFIG.providers.watttime.password)
    if not auth:
        raise ProviderError("Missing ubinascii for Basic auth")
    response = None
    try:
        response = requests.get(CONFIG.providers.watttime.base_url + "/login", headers={"Authorization": auth})
        if response.status_code != 200:
            raise ProviderError("WattTime login HTTP %d" % response.status_code)
        token = (response.json() or {}).get("token")
        if not token:
            raise ProviderError("WattTime login missing token")
        return token
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def _watttime_grid_region(lat, lon, token):
    response = None
    try:
        response = requests.get(
            CONFIG.providers.watttime.base_url + "/v2/ba-from-loc",
            headers={"Authorization": "Bearer " + token},
            params={"latitude": str(lat), "longitude": str(lon)},
        )
        if response.status_code != 200:
            raise ProviderError("WattTime region HTTP %d" % response.status_code)
        payload = response.json() or {}
        region = payload.get("ba") or payload.get("region")
        if not region:
            raise ProviderError("WattTime region missing ba")
        return region
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def fetch_watttime_current(lat, lon):
    if not requests:
        raise ProviderError("urequests not available")
    if not (
        CONFIG.providers.watttime.enabled and CONFIG.providers.watttime.username and CONFIG.providers.watttime.password
    ):
        raise ProviderError("WattTime disabled/missing credentials")
    if not _watttime_allowed_now():
        raise ProviderError("WattTime temporarily disabled")

    token = _watttime_login_token()
    region = _watttime_grid_region(lat, lon, token)

    response = None
    try:
        response = requests.get(
            CONFIG.providers.watttime.base_url + "/v2/index",
            headers={"Authorization": "Bearer " + token},
            params={"ba": region},
        )
        if response.status_code == 403:
            _watttime_disable_for_a_day()
            raise ProviderError("WattTime forbidden, cooling down")
        if response.status_code != 200:
            raise ProviderError("WattTime index HTTP %d" % response.status_code)
        payload = response.json() or {}
        value = safe_float(payload.get("moer"))
        if value is None:
            raise ProviderError("WattTime index missing moer")
        return {"city": region, "history": [{"datetime": epoch_to_iso_z(int(time.time())), "carbonIntensity": value}], "_provider": "watttime"}
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass


def fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del city
    last_error = None
    for provider in provider_order(country_code):
        try:
            if provider == "uk":
                return fetch_uk_ci_window(start_epoch, end_epoch), "uk"
            if provider == "em":
                return fetch_em_past_range(lat, lon, start_epoch, end_epoch), "em"
            if provider == "watttime":
                return fetch_watttime_current(lat, lon), "watttime"
            if provider == "entsoe":
                return fetch_entsoe_window(country_code, start_epoch, end_epoch), "entsoe"
        except Exception as error:
            last_error = error
    raise ProviderError(str(last_error) if last_error else "No providers available")


# =========================
# Display helpers + driver
# =========================


def intensity_zone_from_percentile(percentile_value):
    if percentile_value is None:
        return "mid"
    if percentile_value <= CONFIG.thresholds.green_percentile_max:
        return "low"
    if percentile_value <= CONFIG.thresholds.yellow_percentile_max:
        return "mid"
    return "high"


def led_level_from_percentile(percentile_value):
    if percentile_value is None:
        return 0
    return int(clamp(int(round(percentile_value * 12)), 0, 12))


CMD_SOFT_RESET = 0x12
CMD_DRIVER_OUTPUT_CONTROL = 0x01
CMD_DATA_ENTRY_MODE = 0x11
CMD_RAM_X_WINDOW = 0x44
CMD_RAM_Y_WINDOW = 0x45
CMD_BORDER_WAVEFORM = 0x3C
CMD_RAM_X_POINTER = 0x4E
CMD_RAM_Y_POINTER = 0x4F
CMD_WRITE_BW_RAM = 0x24
CMD_WRITE_RED_RAM = 0x26
CMD_MASTER_ACTIVATION = 0x20
DATA_XY_INCREMENT = 0x03
DATA_BORDER_LUT = 0x05


class EPDWaveshareWS19588:
    WIDTH = EPD_W
    HEIGHT = EPD_H

    def __init__(self):
        if not (framebuf and Pin and SPI):
            raise RuntimeError("machine/framebuf modules unavailable")
        self.reset_pin = Pin(PIN_RST, Pin.OUT)
        self.busy_pin = Pin(PIN_BUSY, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(PIN_CS, Pin.OUT)
        self.dc_pin = Pin(PIN_DC, Pin.OUT)
        self.width = self.WIDTH if self.WIDTH % 8 == 0 else (self.WIDTH // 8) * 8 + 8
        self.height = self.HEIGHT
        self.spi = SPI(SPI_BUS)
        self.spi.init(baudrate=4_000_000)
        size = self.height * self.width // 8
        self.black_buffer = bytearray(size)
        self.red_buffer = bytearray(size)
        self.black_frame = framebuf.FrameBuffer(self.black_buffer, self.width, self.height, framebuf.MONO_HLSB)
        self.red_frame = framebuf.FrameBuffer(self.red_buffer, self.width, self.height, framebuf.MONO_HLSB)
        self.init()

    def digital_write(self, pin, value): pin.value(value)
    def digital_read(self, pin): return pin.value()
    def delay_ms(self, ms): time.sleep(ms / 1000.0)

    def send_command(self, command):
        self.digital_write(self.dc_pin, 0); self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray([command]))
        self.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        self.digital_write(self.dc_pin, 1); self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray([data]))
        self.digital_write(self.cs_pin, 1)

    def send_data_buffer(self, buf):
        self.digital_write(self.dc_pin, 1); self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)

    def wait_until_idle(self):
        while self.digital_read(self.busy_pin) == BUSY_ACTIVE:
            self.delay_ms(10)
        self.delay_ms(20)

    def reset(self):
        self.digital_write(self.reset_pin, 1); self.delay_ms(50)
        self.digital_write(self.reset_pin, 0); self.delay_ms(2)
        self.digital_write(self.reset_pin, 1); self.delay_ms(50)

    def set_windows(self, x_start, y_start, x_end, y_end):
        self.send_command(CMD_RAM_X_WINDOW)
        self.send_data((x_start >> 3) & 0xFF); self.send_data((x_end >> 3) & 0xFF)
        self.send_command(CMD_RAM_Y_WINDOW)
        self.send_data(y_start & 0xFF); self.send_data((y_start >> 8) & 0xFF)
        self.send_data(y_end & 0xFF); self.send_data((y_end >> 8) & 0xFF)

    def set_cursor(self, x_start, y_start):
        self.send_command(CMD_RAM_X_POINTER); self.send_data(x_start & 0xFF)
        self.send_command(CMD_RAM_Y_POINTER); self.send_data(y_start & 0xFF); self.send_data((y_start >> 8) & 0xFF)

    def init(self):
        self.reset(); self.wait_until_idle(); self.send_command(CMD_SOFT_RESET); self.wait_until_idle()
        self.send_command(CMD_DRIVER_OUTPUT_CONTROL); self.send_data(0xF9); self.send_data(0x00); self.send_data(0x00)
        self.send_command(CMD_DATA_ENTRY_MODE); self.send_data(DATA_XY_INCREMENT)
        self.set_windows(0, 0, self.width - 1, self.height - 1); self.set_cursor(0, 0)
        self.send_command(CMD_BORDER_WAVEFORM); self.send_data(DATA_BORDER_LUT)
        self.send_command(0x18); self.send_data(0x80)
        self.send_command(0x21); self.send_data(0x80); self.send_data(0x80)
        self.wait_until_idle()

    def clear(self):
        self.black_frame.fill(1)
        self.red_frame.fill(1)

    def display(self):
        self.send_command(CMD_WRITE_BW_RAM); self.send_data_buffer(self.black_buffer)
        self.send_command(CMD_WRITE_RED_RAM); self.send_data_buffer(self.red_buffer)
        self.send_command(CMD_MASTER_ACTIVATION); self.wait_until_idle()


EPD2in13BWR = EPDWaveshareWS19588


FONT5x8 = {
    " ": [0x00, 0x00, 0x00, 0x00, 0x00],
    "!": [0x00, 0x00, 0x5F, 0x00, 0x00],
    '"': [0x00, 0x07, 0x00, 0x07, 0x00],
    "#": [0x14, 0x7F, 0x14, 0x7F, 0x14],
    "$": [0x24, 0x2A, 0x7F, 0x2A, 0x12],
    "%": [0x23, 0x13, 0x08, 0x64, 0x62],
    "&": [0x36, 0x49, 0x55, 0x22, 0x50],
    "'": [0x00, 0x05, 0x03, 0x00, 0x00],
    "(": [0x00, 0x1C, 0x22, 0x41, 0x00],
    ")": [0x00, 0x41, 0x22, 0x1C, 0x00],
    "*": [0x14, 0x08, 0x3E, 0x08, 0x14],
    "+": [0x08, 0x08, 0x3E, 0x08, 0x08],
    ",": [0x00, 0x50, 0x30, 0x00, 0x00],
    "-": [0x08, 0x08, 0x08, 0x08, 0x08],
    ".": [0x00, 0x60, 0x60, 0x00, 0x00],
    "/": [0x20, 0x10, 0x08, 0x04, 0x02],
    "0": [0x3E, 0x51, 0x49, 0x45, 0x3E],
    "1": [0x00, 0x42, 0x7F, 0x40, 0x00],
    "2": [0x62, 0x51, 0x49, 0x49, 0x46],
    "3": [0x22, 0x41, 0x49, 0x49, 0x36],
    "4": [0x18, 0x14, 0x12, 0x7F, 0x10],
    "5": [0x2F, 0x49, 0x49, 0x49, 0x31],
    "6": [0x3E, 0x49, 0x49, 0x49, 0x32],
    "7": [0x01, 0x71, 0x09, 0x05, 0x03],
    "8": [0x36, 0x49, 0x49, 0x49, 0x36],
    "9": [0x26, 0x49, 0x49, 0x49, 0x3E],
    ":": [0x00, 0x36, 0x36, 0x00, 0x00],
    ";": [0x00, 0x56, 0x36, 0x00, 0x00],
    "<": [0x08, 0x14, 0x22, 0x41, 0x00],
    "=": [0x14, 0x14, 0x14, 0x14, 0x14],
    ">": [0x00, 0x41, 0x22, 0x14, 0x08],
    "?": [0x02, 0x01, 0x59, 0x09, 0x06],
    "@": [0x3E, 0x41, 0x5D, 0x59, 0x4E],
    "A": [0x7E, 0x11, 0x11, 0x11, 0x7E],
    "B": [0x7F, 0x49, 0x49, 0x49, 0x36],
    "C": [0x3E, 0x41, 0x41, 0x41, 0x22],
    "D": [0x7F, 0x41, 0x41, 0x22, 0x1C],
    "E": [0x7F, 0x49, 0x49, 0x49, 0x41],
    "F": [0x7F, 0x09, 0x09, 0x09, 0x01],
    "G": [0x3E, 0x41, 0x49, 0x49, 0x7A],
    "H": [0x7F, 0x08, 0x08, 0x08, 0x7F],
    "I": [0x00, 0x41, 0x7F, 0x41, 0x00],
    "J": [0x20, 0x40, 0x41, 0x3F, 0x01],
    "K": [0x7F, 0x08, 0x14, 0x22, 0x41],
    "L": [0x7F, 0x40, 0x40, 0x40, 0x40],
    "M": [0x7F, 0x02, 0x04, 0x02, 0x7F],
    "N": [0x7F, 0x04, 0x08, 0x10, 0x7F],
    "O": [0x3E, 0x41, 0x41, 0x41, 0x3E],
    "P": [0x7F, 0x09, 0x09, 0x09, 0x06],
    "Q": [0x3E, 0x41, 0x51, 0x21, 0x5E],
    "R": [0x7F, 0x09, 0x19, 0x29, 0x46],
    "S": [0x46, 0x49, 0x49, 0x49, 0x31],
    "T": [0x01, 0x01, 0x7F, 0x01, 0x01],
    "U": [0x3F, 0x40, 0x40, 0x40, 0x3F],
    "V": [0x1F, 0x20, 0x40, 0x20, 0x1F],
    "W": [0x3F, 0x40, 0x38, 0x40, 0x3F],
    "X": [0x63, 0x14, 0x08, 0x14, 0x63],
    "Y": [0x07, 0x08, 0x70, 0x08, 0x07],
    "Z": [0x61, 0x51, 0x49, 0x45, 0x43],
    "[": [0x00, 0x7F, 0x41, 0x41, 0x00],
    "\\": [0x02, 0x04, 0x08, 0x10, 0x20],
    "]": [0x00, 0x41, 0x41, 0x7F, 0x00],
    "^": [0x04, 0x02, 0x01, 0x02, 0x04],
    "_": [0x40, 0x40, 0x40, 0x40, 0x40],
    "`": [0x00, 0x01, 0x02, 0x04, 0x00],
    "a": [0x20, 0x54, 0x54, 0x54, 0x78],
    "b": [0x7F, 0x48, 0x44, 0x44, 0x38],
    "c": [0x38, 0x44, 0x44, 0x44, 0x20],
    "d": [0x38, 0x44, 0x44, 0x48, 0x7F],
    "e": [0x38, 0x54, 0x54, 0x54, 0x18],
    "f": [0x08, 0x7E, 0x09, 0x01, 0x02],
    "g": [0x0C, 0x52, 0x52, 0x52, 0x3E],
    "h": [0x7F, 0x08, 0x04, 0x04, 0x78],
    "i": [0x00, 0x44, 0x7D, 0x40, 0x00],
    "j": [0x20, 0x40, 0x44, 0x3D, 0x00],
    "k": [0x7F, 0x10, 0x28, 0x44, 0x00],
    "l": [0x00, 0x41, 0x7F, 0x40, 0x00],
    "m": [0x7C, 0x04, 0x18, 0x04, 0x78],
    "n": [0x7C, 0x08, 0x04, 0x04, 0x78],
    "o": [0x38, 0x44, 0x44, 0x44, 0x38],
    "p": [0x7C, 0x14, 0x14, 0x14, 0x08],
    "q": [0x08, 0x14, 0x14, 0x18, 0x7C],
    "r": [0x7C, 0x08, 0x04, 0x04, 0x08],
    "s": [0x48, 0x54, 0x54, 0x54, 0x20],
    "t": [0x04, 0x3F, 0x44, 0x40, 0x20],
    "u": [0x3C, 0x40, 0x40, 0x20, 0x7C],
    "v": [0x1C, 0x20, 0x40, 0x20, 0x1C],
    "w": [0x3C, 0x40, 0x30, 0x40, 0x3C],
    "x": [0x44, 0x28, 0x10, 0x28, 0x44],
    "y": [0x0C, 0x50, 0x50, 0x50, 0x3C],
    "z": [0x44, 0x64, 0x54, 0x4C, 0x44],
    "{": [0x00, 0x08, 0x36, 0x41, 0x00],
    "|": [0x00, 0x00, 0x7F, 0x00, 0x00],
    "}": [0x00, 0x41, 0x36, 0x08, 0x00],
    "~": [0x08, 0x08, 0x2A, 0x1C, 0x08],
}


def draw_char(frame, x, y, char, color=0):
    glyph = FONT5x8.get(char)
    if not glyph:
        glyph = FONT5x8.get("?")
    for col, col_data in enumerate(glyph):
        for row in range(8):
            pixel_on = (col_data >> row) & 0x01
            if pixel_on:
                frame.pixel(x + col, y + row, color)


def draw_text(frame, x, y, text, color=0):
    x_pos = x
    for char in text:
        draw_char(frame, x_pos, y, char, color=color)
        x_pos += 6


def draw_rect(frame, x, y, w, h, color=0, fill=False):
    if fill:
        frame.fill_rect(x, y, w, h, color)
    else:
        frame.rect(x, y, w, h, color)


def draw_hline(frame, x, y, w, color=0):
    frame.hline(x, y, w, color)


def draw_vline(frame, x, y, h, color=0):
    frame.vline(x, y, h, color)


def draw_leds(epd, zone, level):
    x, y, led_size, spacing = 5, 5, 7, 3
    for idx in range(12):
        on = idx < level
        target = epd.red_frame if zone == "high" else epd.black_frame
        draw_rect(target, x + idx * (led_size + spacing), y, led_size, 5, 0 if on else 1, fill=on)


def draw_wifi_icon(epd, x, y, connected):
    draw_text(epd.black_frame if connected else epd.red_frame, x, y, "WiFi", color=0)


def draw_time(epd, x, y):
    now = time.localtime()
    draw_text(epd.black_frame, x, y, "%02d:%02d" % (now[3], now[4]), color=0)


def draw_current_panel(epd, current_ci, verdict, next_line):
    draw_text(epd.black_frame, 5, 28, "CO2:")
    draw_text(epd.black_frame, 45, 28, "%d" % int(current_ci))
    draw_text(epd.black_frame, 90, 28, "g")
    draw_rect(epd.black_frame, 5, 40, 112, 40, color=0, fill=False)
    draw_text(epd.black_frame, 10, 46, verdict[:12])
    if next_line:
        draw_text(epd.black_frame, 10, 58, next_line[:18])


def draw_graph(epd, past, future):
    values = (past[-CONFIG.timeline.past_hours :] if past else []) + (future[: CONFIG.timeline.future_hours] if future else [])
    if not values:
        draw_rect(epd.black_frame, 5, 95, 112, 80, color=0, fill=False)
        return
    low, high = min(values), max(values)
    normalized = [0.5 for _ in values] if high == low else [(v - low) / (high - low) for v in values]
    base_x, base_y, width, height = 5, 95, 112, 80
    draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)
    bar_w = max(1, width // max(1, len(normalized)))
    for i, n in enumerate(normalized):
        bar_h = int(round(n * (height - 2)))
        x = base_x + 1 + i * bar_w
        y = base_y + height - 1 - bar_h
        target = epd.black_frame if i < len(past) else epd.red_frame
        draw_rect(target, x, y, bar_w - 1, bar_h, color=0, fill=True)
    draw_vline(epd.black_frame, base_x + 1 + len(past) * bar_w, base_y, height, color=0)


# =========================
# App orchestration
# =========================

_epd = None
_last_render = 0
_cache = TtlCache(CONFIG.cache_refresh_seconds)


def resolve_geo(params):
    lat = safe_float(params.get("lat")) if params else None
    lon = safe_float(params.get("lon")) if params else None
    city = url_decode(params.get("city")) if params else None
    cc = url_decode(params.get("cc")) if params else None
    return (
        lat if lat is not None else CONFIG.defaults.latitude,
        lon if lon is not None else CONFIG.defaults.longitude,
        city if city else CONFIG.defaults.city,
        cc.upper() if cc else CONFIG.defaults.country,
    )


def series_values(series_json):
    out = []
    for p in series_json.get("history") or []:
        v = safe_float(p.get("carbonIntensity"))
        if v is not None:
            out.append(v)
    return out


def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    key = ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)

    def fetch():
        data, provider_used = fetch_window_any(lat, lon, city, cc, start_epoch, end_epoch)
        data["_provider"] = provider_used
        data["lat"] = lat
        data["lon"] = lon
        data["_resolved"] = {"city": city, "cc": cc}
        return data

    return _cache.get_or_set(key, fetch)


def handle_em_window(params):
    now = floor_hour_epoch(int(time.time()))
    back_hours = int(params.get("back_hours") or CONFIG.timeline.back_hours_default)
    lat, lon, city, cc = resolve_geo(params)
    return get_window(lat, lon, city, cc, now - back_hours * 3600, now)


def handle_em_overlay(params):
    now = floor_hour_epoch(int(time.time()))
    lat, lon, city, cc = resolve_geo(params)
    start = now - (7 * 24 * 3600) - (CONFIG.timeline.past_hours * 3600)
    end = now - (7 * 24 * 3600) + (CONFIG.timeline.future_hours * 3600)
    return get_window(lat, lon, city, cc, start, end)


def make_next_line(recommendation):
    wait_hours = recommendation.get("wait_hours")
    if isinstance(wait_hours, int) and wait_hours > 0:
        return "Cleaner in %dh (%s)" % (wait_hours, fmt_hhmm_local(int(time.time()) + wait_hours * 3600))
    return ((recommendation.get("reason") or "") + " " + (recommendation.get("next_best") or "")).strip()[:22]


def handle_status(params, wifi_connected_callback):
    lat, lon, city, cc = resolve_geo(params)
    now = floor_hour_epoch(int(time.time()))
    key = ("status", round(lat, 4), round(lon, 4), city, cc, now)

    def build():
        window_data = handle_em_window({"lat": str(lat), "lon": str(lon), "city": city, "cc": cc, "back_hours": str(CONFIG.timeline.back_hours_default)})
        history = window_data.get("history") or []
        if not history:
            raise ProviderError("No window history")

        current_intensity = safe_float(history[-1].get("carbonIntensity"))
        if current_intensity is None:
            raise ProviderError("No carbonIntensity in last point")

        overlay_data = handle_em_overlay({"lat": str(lat), "lon": str(lon), "city": city, "cc": cc})
        recommendation = recommend_from_week(current_intensity, overlay_data.get("history") or [], CONFIG.timeline.lookahead_hours)

        status = {
            "datetime": epoch_to_iso_z(now),
            "lat": lat,
            "lon": lon,
            "city": city,
            "cc": cc,
            "carbonIntensity": current_intensity,
            "recommendation": recommendation,
            "_provider": window_data.get("_provider") or "—",
        }

        try:
            render_screen(status, window_data, overlay_data, wifi_connected_callback)
        except Exception as error:
            print("[eink] render error:", error)
        return status

    return _cache.get_or_set(key, build)


def render_screen(status_json, window_json, overlay_json, wifi_connected_callback):
    global _epd, _last_render
    now = int(time.time())
    if now - _last_render < CONFIG.display.render_min_interval_sec:
        return
    if _epd is None:
        _epd = EPD2in13BWR()

    current_intensity = safe_float(status_json.get("carbonIntensity")) or 0.0
    recommendation = status_json.get("recommendation") or {}
    verdict = recommendation.get("verdict") or "—"
    next_line = make_next_line(recommendation)

    current_values = series_values(window_json)
    past_values = current_values[-CONFIG.timeline.past_hours :] if len(current_values) >= 2 else []
    overlay_values = series_values(overlay_json)
    future_values = overlay_values[-CONFIG.timeline.future_hours :] if len(overlay_values) >= 2 else []

    percentile_value = percentile(sorted(overlay_values), current_intensity) if len(overlay_values) >= 12 else None
    zone = intensity_zone_from_percentile(percentile_value)
    level = led_level_from_percentile(percentile_value)

    _epd.clear()
    draw_leds(_epd, zone, level)
    draw_time(_epd, 160, 2)
    draw_wifi_icon(_epd, 194, 2, wifi_connected_callback())
    draw_current_panel(_epd, current_intensity, verdict, next_line)
    draw_graph(_epd, past_values, future_values)
    _epd.display()
    _last_render = now


# =========================
# HTTP helpers + server
# =========================


def _readline(conn):
    line = b""
    while True:
        ch = conn.recv(1)
        if not ch:
            break
        line += ch
        if line.endswith(b"\r\n") or len(line) > 2048:
            break
    return line


def parse_request(conn):
    first = _readline(conn).decode().strip()
    if not first:
        return None
    parts = first.split()
    if len(parts) < 2:
        return None
    method, path_qs = parts[0], parts[1]
    while True:
        h = _readline(conn)
        if not h or h == b"\r\n":
            break
    return method, path_qs


def split_path_qs(path_qs):
    if "?" not in path_qs:
        return path_qs, {}
    path, query = path_qs.split("?", 1)
    params = {}
    for pair in query.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
        else:
            k, v = pair, ""
        params[k] = v
    return path, params


def send_json(conn, code, payload):
    try:
        import ujson as json
    except Exception:
        import json
    body = json.dumps(payload)
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())


def serve_forever(wifi_connected_callback):
    addr = socket.getaddrinfo(CONFIG.server.host, CONFIG.server.port)[0][-1]
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(addr)
    server_socket.listen(2)
    print("Pico running: http://%s:%d" % (CONFIG.server.host, CONFIG.server.port))

    while True:
        conn, _ = server_socket.accept()
        try:
            request = parse_request(conn)
            if not request:
                conn.close()
                continue
            method, path_qs = request
            path, params = split_path_qs(path_qs)

            if method != "GET":
                send_json(conn, 405, {"error": "Only GET supported"})
            elif path == "/em/window":
                send_json(conn, 200, handle_em_window(params))
            elif path == "/em/window-overlay":
                send_json(conn, 200, handle_em_overlay(params))
            elif path == "/status":
                send_json(conn, 200, handle_status(params, wifi_connected_callback))
            else:
                send_json(conn, 404, {"error": "Not found", "path": path})
        except Exception as error:
            send_json(conn, 500, {"error": "Internal error", "details": str(error)})
        finally:
            try:
                conn.close()
            except Exception:
                pass
            gc.collect()


# =========================
# Main
# =========================

_wlan = None


def wifi_connect(timeout_ms=15000):
    global _wlan
    if not network:
        return False
    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        return True
    _wlan.connect(CONFIG.wifi.ssid, CONFIG.wifi.password)
    start = time.ticks_ms()
    while not _wlan.isconnected():
        time.sleep_ms(200)
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            return False
    return True


def wifi_ok():
    return bool(_wlan) and _wlan.isconnected()


def main():
    connected = wifi_connect()
    print("WiFi:", "connected" if connected else "not connected")
    if not requests:
        print("WARNING: urequests not available; provider calls will fail.")
    serve_forever(wifi_ok)


if __name__ == "__main__":
    main()
