"""Single-file Pico firmware bundle.

This file is provided so you can copy/paste one script to the device.
It inlines the behavior from the `pico/firmware/*` modules and keeps the
same HTTP API:
- GET /
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
import io
import network
import framebuf
from machine import Pin, SPI
import urequests as requests
import ubinascii
import xmltok
import sys
import ujson
import utime
import struct


# =========================
# Settings / configuration
# =========================
class CONFIG:
    class wifi:
        ssid = "" # TODO: CHANGE ME
        password = "" # TODO: CHANGE ME

    class defaults:
        # ENTSOE
        latitude = 41.9028
        longitude = 12.4964
        city = "Rome"
        country = "IT"

        # UKCI
        #latitude = 51.5072
        #longitude = 0.1276
        #city = "London"
        #country = "GB"

        # ELECTRICITY MAP
        #latitude = 59.3327
        #longitude = 18.0656
        #city = "Stockholm"
        #country = "SE"

        # WATTTIME
        #latitude = 37.7749
        #longitude = 122.4194
        #city = "San Francisco"
        #country = "CAISO_NORTH"

    class providers:
        ukci_enabled = False # TODO: CHANGE ME

        class electricity_maps:
            enabled = False # TODO: CHANGE ME
            token = "" # TODO: CHANGE ME
            base_url = "https://api.electricitymaps.com"

        class watttime:
            enabled = False # TODO: CHANGE ME
            username = "" # TODO: CHANGE ME
            password = "" # TODO: CHANGE ME
            base_url = "https://api.watttime.org"

        # TODO: it's super slow due to XML response
        class entsoe:
            enabled = True # TODO: CHANGE ME
            token = "" # TODO: CHANGE ME
            base_url = "https://web-api.tp.entsoe.eu/api"
            area_override = "IT-CSOUTH" # TODO: CHANGE ME

        watttime_cooldown_sec = 24 * 3600
        force_dummy = False # TODO: CHANGE ME

    class timeline:
        back_hours_default = 48
        past_hours = 36
        future_hours = 12

    class thresholds:
        green_percentile_max = 0.25
        yellow_percentile_max = 0.50

    class server:
        host = "0.0.0.0"
        port = 8080

    class display:
        render_min_interval_sec = 60
        landscape = True

    class geo:
        auto_from_public_ip = True
        ip_lookup_url = "https://ipwho.is/"
        refresh_seconds = 24 * 3600
        failure_retry_seconds = 15 * 60

    cache_refresh_seconds = 300 # 5 mins


# =========================
# E-INK
# =========================

EINK_BLACK = 0
EINK_WHITE = 1


EPD_WIDTH       = 122
EPD_HEIGHT      = 250
RST_PIN         = 12
DC_PIN          = 8
CS_PIN          = 9
BUSY_PIN        = 13


class EPD_2in13_B_V4_Base:
    def __init__(self):
        self.reset_pin = Pin(RST_PIN, Pin.OUT)

        self.busy_pin = Pin(BUSY_PIN, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(CS_PIN, Pin.OUT)
        if EPD_WIDTH % 8 == 0:
            self.width = EPD_WIDTH
        else :
            self.width = (EPD_WIDTH // 8) * 8 + 8
        self.height = EPD_HEIGHT

        self.spi = SPI(1)
        self.spi.init(baudrate=4000_000)
        self.dc_pin = Pin(DC_PIN, Pin.OUT)

        self.buffer_black = bytearray(self.height * self.width // 8)
        self.buffer_red = bytearray(self.height * self.width // 8)

    def init(self):
        log('Init e-ink')
        self.reset()

        self.ReadBusy()
        self.send_command(0x12)  #SWRESET
        self.ReadBusy()

        self.send_command(0x01) #Driver output control
        self.send_data(0xf9)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x11) #data entry mode
        self.send_data(self.command_code)

        self.SetWindows(0, 0, self.width-1, self.height-1)
        self.SetCursor(0, 0)

        self.send_command(0x3C) #BorderWaveform
        self.send_data(0x05)

        self.send_command(0x18) #Read built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x21) #  Display update control
        self.send_data(0x80)
        self.send_data(0x80)

        self.ReadBusy()

        return 0

    def digital_write(self, pin, value):
        pin.value(value)

    def digital_read(self, pin):
        return pin.value()

    def delay_ms(self, delaytime):
        utime.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    def module_exit(self):
        self.digital_write(self.reset_pin, 0)

    # Hardware reset
    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)


    def send_command(self, command):
        self.digital_write(self.dc_pin, 0)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([command])
        self.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([data])
        self.digital_write(self.cs_pin, 1)

    def send_data1(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        while(self.digital_read(self.busy_pin) == 1):
            self.delay_ms(10)
        self.delay_ms(20)

    def TurnOnDisplay(self):
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        self.send_command(0x44) # SET_RAM_X_ADDRESS_START_END_POSITION
        self.send_data((Xstart>>3) & 0xFF)
        self.send_data((Xend>>3) & 0xFF)

        self.send_command(0x45) # SET_RAM_Y_ADDRESS_START_END_POSITION
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)
        self.send_data(Yend & 0xFF)
        self.send_data((Yend >> 8) & 0xFF)

    def SetCursor(self, Xstart, Ystart):
        self.send_command(0x4E) # SET_RAM_X_ADDRESS_COUNTER
        self.send_data(Xstart & 0xFF)

        self.send_command(0x4F) # SET_RAM_Y_ADDRESS_COUNTER
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)

    def Clear(self, colorblack, colorred):
        self.send_command(0x24)
        self.send_data1([colorblack] * self.height * int(self.width / 8))

        self.send_command(0x26)
        self.send_data1([colorred] * self.height * int(self.width / 8))

        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0x10)
        self.send_data(0x01)

        self.delay_ms(2000)
        self.module_exit()

    def display(self):
        self.send_command(0x24)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(0, self.height):
                self.send_data(self.buffer_black[i + j * self.height])

        self.send_command(0x26)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(0, self.height):
                self.send_data(self.buffer_red[i + j * self.height])

        self.TurnOnDisplay()

# TODO: TEST IT
class EPD_2in13_B_V4_Portrait(EPD_2in13_B_V4_Base):
    def __init__(self):
        super(EPD_2in13_B_V4_Portrait, self).__init__()

        self.command_code = 0x03

        self.imageblack = framebuf.FrameBuffer(self.buffer_black, self.width, self.height, framebuf.MONO_HLSB)
        self.imagered = framebuf.FrameBuffer(self.buffer_red, self.width, self.height, framebuf.MONO_HLSB)
        self.init()

class EPD_2in13_B_V4_Landscape(EPD_2in13_B_V4_Base):
    def __init__(self):
        super(EPD_2in13_B_V4_Landscape, self).__init__()

        self.command_code = 0x07

        self.imageblack = framebuf.FrameBuffer(self.buffer_black, self.height, self.width, framebuf.MONO_VLSB)
        self.imagered = framebuf.FrameBuffer(self.buffer_red, self.height, self.width, framebuf.MONO_VLSB)
        self.init()


# =========================
# Shared utils
# =========================


def free_mem():
    log("Memory before free: %d KB" % int(gc.mem_free() / 1024))
    gc.collect()
    log("Memory after free: %d KB" % int(gc.mem_free() / 1024))


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


def close_response(response):
    if response:
        try:
            response.close()
        except Exception:
            pass


def http_get(url, error_label, headers=None, auth=None):
    if not requests:
        raise ProviderError("urequests not available")

    response = requests.get(url, headers=headers, auth=auth)
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
        return "%04d-%02d-%02d%s%02d:%02d:%02d" % (year, month, day, separator, hour, minute, second)
    return "%04d-%02d-%02d%s%02d:%02d" % (year, month, day, separator, hour, minute)


def _now_stamp():
    return _format_timestamp(time.localtime(), include_seconds=True, separator=" ")


def log(*parts):
    print("[%s]" % _now_stamp(), *parts)


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
                idx = plus if plus > minus else minus
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
        key_str = " ".join(str(x) for x in key)
        log("Fetching from key '%s'" % key_str)
        value = self.get(key)
        if value is not None:
            log("Key '%s' is cached" % key_str)
            return value
        log("Key '%s' is not cached" % key_str)
        return self.set(key, factory())


# =========================
# Providers
# =========================

# https://eepublicdownloads.entsoe.eu/clean-documents/EDI/Library/old-downloads/Market_Areas_v1.0.pdf
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
        value = cast_float(intensity_getter(point))
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


# =========================
# Rendering on Pico (display + UI)
# =========================

def get_epd():
    global _epd
    if _epd is None:
        if CONFIG.display.landscape:
            _epd = EPD_2in13_B_V4_Landscape()
        else:
            _epd = EPD_2in13_B_V4_Portrait()
        epd_bind_frames(_epd)

    return _epd

def epd_bind_frames(epd):
    """Normalize framebuffer attribute names across driver variants."""
    if not hasattr(epd, "black_frame"):
        fb = getattr(epd, "imageblack", None)
        if fb is not None:
            epd.black_frame = fb
    if not hasattr(epd, "red_frame"):
        fb = getattr(epd, "imagered", None)
        if fb is not None:
            epd.red_frame = fb

    if not hasattr(epd, "black_buffer"):
        buf = getattr(epd, "buffer_balck", None)
        if buf is not None:
            epd.black_buffer = buf
    if not hasattr(epd, "red_buffer"):
        buf = getattr(epd, "buffer_red", None)
        if buf is not None:
            epd.red_buffer = buf


def epd_clear_screen(epd):
    """Compatibility clear across driver variants (clear vs Clear)."""
    log("Clearing e-ink")
    epd_bind_frames(epd)

    # Prefer direct framebuffer clear so backing buffers are always reset.
    if hasattr(epd, "black_frame") and hasattr(epd, "red_frame"):
        epd.black_frame.fill(EINK_WHITE)
        epd.red_frame.fill(EINK_WHITE)
        return

    clear_upper = getattr(epd, "Clear", None)
    if callable(clear_upper):
        # 0xFF = white for both planes in Waveshare reference driver.
        clear_upper(0xFF, 0xFF)
        return


def panel_dimensions(epd):
    frame = getattr(epd, "black_frame", None)
    frame_w = getattr(frame, "width", None)
    frame_h = getattr(frame, "height", None)
    if frame_w is not None and frame_h is not None:
        return int(frame_w), int(frame_h)

    width = int(getattr(epd, "width", 128))
    height = int(getattr(epd, "height", 250))
    if CONFIG.display.landscape:
        return height, width
    return width, height



def intensity_zone_from_percentile(percentile_value):
    if percentile_value is None:
        return "mid"
    if percentile_value <= CONFIG.thresholds.green_percentile_max:
        return "low"
    if percentile_value <= CONFIG.thresholds.yellow_percentile_max:
        return "mid"
    return "high"

_number_leds = 8
def led_level_from_percentile(percentile_value):
    if percentile_value is None:
        return 0
    return int(clamp(int(round(percentile_value * _number_leds)), 0, _number_leds))


def draw_text(frame, x, y, text, color=0):
    # Use framebuf native font rendering (8px high) for speed and size.
    frame.text(str(text), int(x), int(y), color)


def draw_text_bold(frame, x, y, text, color=0):
    # Simulate bold by drawing twice with one-pixel horizontal offset.
    draw_text(frame, x, y, text, color=color)
    draw_text(frame, x + 1, y, text, color=color)


def draw_rect(frame, x, y, w, h, color=0, fill=False):
    if fill:
        frame.fill_rect(x, y, w, h, color)
    else:
        frame.rect(x, y, w, h, color)


def draw_vline(frame, x, y, h, color=0):
    frame.vline(x, y, h, color)


def draw_leds(epd, zone, level):
    fb = _fb(epd)
    # Draw 8 small "LED" blocks top-left
    # Clear the LED area first (white)
    start_x = 6
    start_y = 10
    fb.fill_rect(start_x, start_y, 56, 12, EINK_WHITE)
    for i in range(_number_leds):
        # filled black if ON, outline if OFF
        x = start_x + i * 7
        if i < int(level):
            fb.fill_rect(x, start_y, 6, 5, EINK_BLACK)
        else:
            fb.rect(x, start_y, 6, 5, EINK_BLACK)


def draw_wifi_icon(epd, x, y, connected, bars=0):
    frame = epd.black_frame if connected else epd.red_frame

    # Clear icon area (about 16x12)
    epd.black_frame.fill_rect(x, y, 16, 12, EINK_WHITE)
    epd.red_frame.fill_rect(x, y, 16, 12, EINK_WHITE)

    bars = int(clamp(int(bars), 0, 4)) if connected else 0

    # Bars from left to right (signal strength style)
    bar_w = 2
    gap = 1
    for i in range(4):
        bx = x + i * (bar_w + gap)
        bar_h = 3 + i * 2
        by = y + 11 - bar_h
        if i < bars:
            frame.fill_rect(bx, by, bar_w, bar_h, EINK_BLACK)
        else:
            epd.red_frame.rect(bx, by, bar_w, bar_h, EINK_BLACK)

    # Antenna dot
    if connected:
        frame.fill_rect(x + 13, y + 9, 2, 2, EINK_BLACK)
    else:
        frame.rect(x + 13, y + 9, 2, 2, EINK_BLACK)

def _fb(epd):
    # Always draw on the black layer framebuffer
    return epd.black_frame


def draw_time(epd, x, y):
    t = time.localtime()
    s = "%02d:%02d" % (t[3], t[4])
    fb = _fb(epd)
    # Native framebuf text is 8x8 per character; clear only the printed area.
    text_w = len(s) * 8
    text_h = 8
    fb.fill_rect(int(x), int(y), text_w, text_h, EINK_WHITE)
    draw_text(fb, x, y, s)

def draw_current_panel(epd, current_ci, verdict, next_line):
    verdict = (verdict or "").strip()
    warning_mode = verdict not in ("OK", "RUN NOW")

    screen_w, _ = panel_dimensions(epd)
    panel_x, panel_y, panel_h = 5, 20, 25
    panel_w = max(40, screen_w - 10)

    # Clear panel area first.
    epd.black_frame.fill_rect(panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_WHITE)
    epd.red_frame.fill_rect(panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_WHITE)

    # Black background + white text.
    text_frame = epd.black_frame
    if warning_mode:
        # Red background + white text.
        text_frame = epd.red_frame
    text_frame.fill_rect(panel_x + 1, panel_y + 1, panel_w - 2, panel_h - 2, EINK_BLACK)
    text_color = EINK_WHITE

    text_x = panel_x + 5
    text_y = panel_y + 8

    def _draw_verdict_line(x, y, text):
        draw_text_bold(text_frame, x, y, text, color=text_color)

    if warning_mode:
        _draw_verdict_line(text_x, text_y, next_line)
    else:
        _draw_verdict_line(text_x, text_y, verdict)

    draw_text(epd.black_frame, 5, 47, "CO2: %d g/kWh" % int(current_ci))


def draw_graph(epd, current_line, week_line):
    graph_hours = CONFIG.timeline.back_hours_default + CONFIG.timeline.future_hours
    if not current_line and not week_line:
        draw_rect(epd.black_frame, 5, 55, 112, 80, color=0, fill=False)
        return

    screen_w, screen_h = panel_dimensions(epd)

    base_x, base_y = 5, 60
    width = max(10, screen_w - 10)
    height = max(10, min(90, screen_h - base_y - 5))

    if not current_line and not week_line:
        draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)
        return

    tick_band = 9
    plot_h = max(8, height - tick_band)
    draw_rect(epd.black_frame, base_x, base_y, width, height, color=0, fill=False)

    # Y-scale from min/max over last week + current timeline values.
    scale_values = [v for v in current_line + week_line if isinstance(v, (int, float))]
    if not scale_values:
        return
    low, high = min(scale_values), max(scale_values)
    
    def norm(v):
        if v is None:
            return None
        if high == low:
            return 0.5
        return (v - low) / (high - low)

    normalized_current = [norm(v) for v in current_line]
    normalized_week = [norm(v) for v in week_line]

    npts = min(graph_hours, max(len(normalized_current), len(normalized_week)))
    if npts < 2:
        return

    inner_w = max(1, width - 2)
    step_x = inner_w / float(max(1, npts - 1))

    def x_at(i):
        return base_x + 1 + int(round(i * step_x))

    def y_from_norm(n):
        n = min(1.0, max(0.0, n))
        return base_y + (plot_h - 2) - int(round(n * (plot_h - 3)))

    def draw_line(target_frame, values, dotted=False):
        for i in range(npts - 1):
            a = values[i] if i < len(values) else None
            b = values[i + 1] if i + 1 < len(values) else None
            if a is None or b is None:
                continue
            x1, y1 = x_at(i), y_from_norm(a)
            x2, y2 = x_at(i + 1), y_from_norm(b)
            if not dotted:
                target_frame.line(x1, y1, x2, y2, EINK_BLACK)
                continue
            dx, dy = x2 - x1, y2 - y1
            steps = max(abs(dx), abs(dy))
            if steps <= 0:
                continue
            for s in range(0, steps + 1, 2):
                px = x1 + (dx * s) // steps
                py = y1 + (dy * s) // steps
                target_frame.pixel(px, py, EINK_BLACK)

    # Current timeline: solid black. Previous-week timeline: dotted black.
    draw_line(epd.black_frame, normalized_current, dotted=False)
    draw_line(epd.black_frame, normalized_week, dotted=True)
    
    # Red dashed threshold bands (percentile cutoffs) across the graph.
    def draw_dashed_hline(x0, x1, y, dash=3, gap=5):
        x = int(x0)
        x1 = int(x1)
        y = int(y)
        while x <= x1:
            seg_end = min(x + dash - 1, x1)
            seg_w = max(1, seg_end - x + 1)

            epd.black_frame.hline(x, y, seg_w, EINK_WHITE)
            epd.red_frame.hline(x, y, seg_w, EINK_BLACK)
            x = seg_end + gap + 1

    def value_at_percentile(sorted_values, p):
        if not sorted_values:
            return None
        p = min(1.0, max(0.0, float(p)))
        if len(sorted_values) == 1:
            return sorted_values[0]
        pos = p * (len(sorted_values) - 1)
        lo = int(pos)
        hi = lo + 1
        if hi >= len(sorted_values):
            return sorted_values[lo]
        frac = pos - lo
        return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac

    threshold_percentiles = (
        CONFIG.thresholds.green_percentile_max,
        CONFIG.thresholds.yellow_percentile_max,
    )
    sorted_scale = sorted(scale_values)
    x0 = base_x + 1
    x1 = base_x + width - 2
    for p in threshold_percentiles:
        v = value_at_percentile(sorted_scale, p)
        if v is None:
            continue
        draw_dashed_hline(x0, x1, y_from_norm(norm(v)))

    # "now" marker line
    now_idx = CONFIG.timeline.back_hours_default
    if 0 <= now_idx < npts:
        draw_vline(epd.black_frame, x_at(now_idx), base_y + 1, max(1, plot_h - 1), color=EINK_BLACK)

    # Day ticks and labels (-48h, -24h, now)
    tick_y0 = base_y + plot_h
    tick_y1 = base_y + height - 2
    labels = [(-48, "-2d"), (-24, "-1d"), (0, "now")]
    for hour_offset, label in labels:
        idx = hour_offset + CONFIG.timeline.back_hours_default
        if idx < 0 or idx >= npts:
            continue
        x = x_at(idx)
        draw_vline(epd.black_frame, x, tick_y0, max(1, tick_y1 - tick_y0 + 1), color=EINK_BLACK)
        draw_text(epd.black_frame, max(base_x + 1, x - 8), base_y + height - 8, label, color=EINK_BLACK)



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

    if current_percentile <= CONFIG.thresholds.green_percentile_max:
        return {"verdict": "RUN NOW", "reason": "Cleaner than avg", "next_best": "Now", "wait_hours": 0}
    if current_percentile <= CONFIG.thresholds.yellow_percentile_max:
        return {"verdict": "OK", "reason": "Around average", "next_best": next_best, "wait_hours": wait_hours or 0}
    return {"verdict": "WAIT", "reason": "Dirtier than avg", "next_best": next_best, "wait_hours": wait_hours}


def _compute_next_best(overlay_history, now_epoch):
    best = None
    horizon_epoch = now_epoch + (CONFIG.timeline.future_hours * 3600)
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
# Fetching data + app orchestration
# =========================

_epd = None
_server_socket = None
_last_render = 0
_cache = TtlCache(CONFIG.cache_refresh_seconds)
_auto_geo_cache = None
_auto_geo_expires = 0


def _auto_geo_defaults():
    global _auto_geo_cache, _auto_geo_expires

    if not CONFIG.geo.auto_from_public_ip:
        return None

    now = time.time()
    if _auto_geo_cache and now < _auto_geo_expires:
        return _auto_geo_cache

    try:
        payload = http_get_json(CONFIG.geo.ip_lookup_url, "IP geo")
        if payload.get("success") is False:
            raise ProviderError("IP geo lookup failed")

        lat = safe_float(payload.get("latitude"))
        lon = safe_float(payload.get("longitude"))
        city = (payload.get("city") or payload.get("region") or "").strip()
        cc = (payload.get("country_code") or "").strip().upper()

        if lat is None or lon is None or not city or not cc:
            raise ProviderError("IP geo incomplete payload")

        _auto_geo_cache = {"lat": lat, "lon": lon, "city": city, "cc": cc}
        _auto_geo_expires = now + int(CONFIG.geo.refresh_seconds)
        log("Auto-geo resolved to %s, %s (%s, %s)" % (city, cc, str(lat), str(lon)))
        return _auto_geo_cache
    except Exception as error:
        log("Auto-geo failed:", error)
        _auto_geo_expires = now + int(CONFIG.geo.failure_retry_seconds)
        return _auto_geo_cache


def resolve_geo(params):
    lat = safe_float(params.get("lat")) if params else None
    lon = safe_float(params.get("lon")) if params else None
    city = url_decode(params.get("city")) if params else None
    cc = url_decode(params.get("cc")) if params else None

    auto_geo = _auto_geo_defaults() or {
        "lat": CONFIG.defaults.latitude,
        "lon": CONFIG.defaults.longitude,
        "city": CONFIG.defaults.city,
        "cc": CONFIG.defaults.country,
    }

    return (
        lat if lat is not None else auto_geo["lat"],
        lon if lon is not None else auto_geo["lon"],
        city if city else auto_geo["city"],
        cc.upper() if cc else auto_geo["cc"],
    )


def series_values(series_json):
    out = []
    for p in series_json.get("history") or []:
        v = safe_float(p.get("carbonIntensity"))
        if v is not None:
            out.append(v)
    return out


def series_points(series_json):
    points = []
    for p in series_json.get("history") or []:
        ts = iso_z_to_epoch(p.get("datetime"))
        v = safe_float(p.get("carbonIntensity"))
        if ts is not None and v is not None:
            points.append((floor_hour_epoch(ts), v))
    points.sort(key=lambda item: item[0])
    return points

# TODO: add a variable to force switch the provide and the city
_dummy_rng_state = int(time.time()) & 0x7FFFFFFF
def _rand01():
    global _dummy_rng_state
    # Deterministic LCG; avoids depending on CPython random module in MicroPython.
    _dummy_rng_state = (1103515245 * _dummy_rng_state + 12345) & 0x7FFFFFFF
    return (_dummy_rng_state % 10000) / 10000.0


def dummy_fetch_window_any(lat, lon, city, country_code, start_epoch, end_epoch):
    del lat, lon, city, country_code
    DUMMY_SERIES_SEED = [430, 410, 395, 380, 360, 345, 330, 320, 315, 325, 340, 365]
    min_ci = min(DUMMY_SERIES_SEED)
    max_ci = max(DUMMY_SERIES_SEED)

    history = []
    cursor = floor_hour_epoch(int(start_epoch))
    end_h = floor_hour_epoch(int(end_epoch))
    while cursor <= end_h:
        value = int(round(min_ci + _rand01() * (max_ci - min_ci)))
        history.append({"datetime": epoch_to_iso_z(cursor), "carbonIntensity": value})
        cursor += 3600

    if history:
        log("DUMMY provider generated %d points in range [%d, %d]" % (len(history), min_ci, max_ci))
    return {"city": "Dummy", "history": history, "_provider": "dummy"}, "dummy"


_fresh_data = False
def get_window(lat, lon, city, cc, start_epoch, end_epoch):
    global _fresh_data
    key = ("window", round(lat, 4), round(lon, 4), city, cc, start_epoch, end_epoch)
    _fresh_data = False

    def fetch():
        global _fresh_data
        _fresh_data = True
        log("Fetching data...")
        if CONFIG.providers.force_dummy:
            data, provider_used = dummy_fetch_window_any(lat, lon, city, cc, start_epoch, end_epoch)
        else:
            data, provider_used = fetch_window_any(lat, lon, city, cc, start_epoch, end_epoch)
        log("Provider used: %s" % provider_used)
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
    # Previous-week window matching [-48h, +12h] of the current timeline.
    start = now - (7 * 24 * 3600) - (CONFIG.timeline.back_hours_default * 3600)
    end = now - (7 * 24 * 3600) + (CONFIG.timeline.future_hours * 3600)
    return get_window(lat, lon, city, cc, start, end)


def make_next_line(recommendation):
    wait_hours = recommendation.get("wait_hours")
    if isinstance(wait_hours, int) and wait_hours > 0:
        return "WAIT %dh (%s)" % (wait_hours, fmt_hhmm_local(int(time.time()) + wait_hours * 3600))
    return ((recommendation.get("reason") or "")).strip()[:22] # TODO: THIS LINE IS NOT REALLY NEEDED

def build_status_bundle(params):
    log("Fetching data")
    lat, lon, city, cc = resolve_geo(params)
    now = floor_hour_epoch(int(time.time()))

    window_data = handle_em_window({
        "lat": str(lat), "lon": str(lon), "city": city, "cc": cc,
        "back_hours": str(CONFIG.timeline.back_hours_default),
    })
    history = window_data.get("history") or []
    if not history:
        raise ProviderError("No window history")

    current_intensity = safe_float(history[-1].get("carbonIntensity"))
    if current_intensity is None:
        raise ProviderError("No carbonIntensity in last point")

    overlay_data = handle_em_overlay({"lat": str(lat), "lon": str(lon), "city": city, "cc": cc})
    recommendation = recommend_from_week(
        current_intensity,
        overlay_data.get("history") or [],
        CONFIG.timeline.future_hours,
    )
    log("Finished fetching data")

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

    return status, window_data, overlay_data

def handle_status(params):
    lat, lon, city, cc = resolve_geo(params)
    # Keep a stable key so /status serves cached payload immediately when present.
    # Freshness is managed by TtlCache(CONFIG.cache_refresh_seconds).
    key = ("status", round(lat, 4), round(lon, 4), city, cc)

    def build():
        status, _, _ = build_status_bundle(params)
        return status

    return _cache.get_or_set(key, build)

# ---- Periodic e-ink refresh (decoupled from HTTP polling) ----
_last_display_tick = 0

def _display_tick():
    """Refresh the e-ink every CONFIG.display.render_min_interval_sec even if /status is never called."""
    global _last_display_tick
    now = int(time.time())
    if now - _last_display_tick < CONFIG.display.render_min_interval_sec:
        log("Wait...")
        return
    _last_display_tick = now

    # Choose default params for your device (same as you use when calling /status)
    # If you already have a default location mechanism, use that.
    params = {}  # or {"city": "..."} etc, whatever resolve_geo() supports

    try:
        status, window_data, overlay_data = build_status_bundle(params)
        render_screen(status, window_data, overlay_data)
    except Exception as e:
       # Don't crash the server loop if provider/network is down
        try:
            log("ERROR(_display_tick)", e)
            render_placeholder_screen("DATA ERROR", str(e))
        except Exception as e:
            log("ERROR(_display_tick 2)", e)
            pass

def draw_top_bar(_epd):
    draw_wifi_icon(_epd, 180, 5, wifi_ok(), wifi_signal_bars())
    draw_time(_epd, 205, 8)
    

def render_placeholder_screen(title, detail):
    global _epd, _has_rendered_data
    _epd = get_epd()

    epd_clear_screen(_epd)
    screen_w, _ = panel_dimensions(_epd)
    panel_w = max(40, screen_w - 10)
    draw_rect(_epd.black_frame, 5, 20, panel_w, 25, color=EINK_BLACK, fill=False)

    title = (title or "Status")
    draw_text(_epd.black_frame, 10, 28, title, color=EINK_BLACK)

    if detail:
        detail_text = str(detail)
        if title == "DATA ERROR":
            # Show the error across two lines for readability on failure screen.
            draw_text(_epd.red_frame, 5, 50, detail_text[:50], color=EINK_BLACK)
            draw_text(_epd.red_frame, 5, 57, detail_text[51:10], color=EINK_BLACK)
        else:
            draw_text(_epd.black_frame, 5, 50, str(detail), color=EINK_BLACK)
    draw_top_bar(_epd)
    _epd.display()


def render_screen(status_json, window_json, overlay_json):
    global _epd, _last_render
    now = int(time.time())
    if now - _last_render < CONFIG.display.render_min_interval_sec:
        log("Wait...")
        return
    _epd = get_epd()

    current_intensity = safe_float(status_json.get("carbonIntensity")) or 0.0
    recommendation = status_json.get("recommendation") or {}
    verdict = recommendation.get("verdict") or "—"
    next_line = make_next_line(recommendation)

    now_epoch = floor_hour_epoch(int(time.time()))
    current_points = series_points(window_json)
    overlay_points = series_points(overlay_json)

    # Build aligned 60-hour timeline: [-48h, +12h]
    timeline = [now_epoch - (CONFIG.timeline.back_hours_default * 3600) + i * 3600 for i in range(60)]
    current_map = {ts: v for ts, v in current_points}
    week_map = {ts + (7 * 24 * 3600): v for ts, v in overlay_points}
    current_line = [current_map.get(ts) for ts in timeline]
    week_line = [week_map.get(ts) for ts in timeline]

    overlay_values = [v for _, v in overlay_points]
    percentile_value = percentile(sorted(overlay_values), current_intensity) if len(overlay_values) >= 12 else None
    zone = intensity_zone_from_percentile(percentile_value)
    level = led_level_from_percentile(percentile_value)

    if _fresh_data:
        epd_clear_screen(_epd)

    draw_leds(_epd, zone, level)
    draw_current_panel(_epd, current_intensity, verdict, next_line)
    draw_graph(_epd, current_line, week_line)
    draw_top_bar(_epd)

    _epd.display()
    _last_render = now
    
    free_mem()


# =========================
# Web server
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
    body = ujson.dumps(payload)
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())



def send_html(conn, code, body):
    headers = (
        "HTTP/1.1 %d OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "Content-Length: %d\r\n\r\n"
    ) % (code, len(body))
    conn.send(headers.encode())
    conn.send(body.encode())


def build_index_html():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pico CO₂ Status</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f3f4f6; color: #111827; }
    .page { max-width: 740px; margin: 0 auto; padding: 18px; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.08); padding: 14px; margin-bottom: 12px; }
    h1 { margin: 0 0 8px 0; font-size: 22px; }
    .muted { color: #6b7280; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; }
    .k { font-size: 12px; color: #6b7280; }
    .v { font-weight: 600; margin-top: 2px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
    button { border: none; border-radius: 8px; padding: 8px 12px; background: #2563eb; color: #fff; cursor: pointer; font-weight: 600; }
    .themeBtn { background: #4b5563; }
    .pill { display: inline-block; border-radius: 999px; background: #e5e7eb; padding: 2px 8px; font-size: 12px; font-weight: 600; color: #111827; }
    .ok { background: #d1fae5; color: #065f46; }
    .wait { background: #fef3c7; color: #92400e; }
    .no { background: #fee2e2; color: #991b1b; }
    body.dark { background: #111827; color: #f9fafb; }
    body.dark .card { background: #1f2937; border-color: #374151; }
    body.dark .muted, body.dark .k { color: #9ca3af; }
    body.dark .pill { background: #374151; color: #f9fafb; }
    @media (prefers-color-scheme: dark) {
      body.auto { background: #111827; color: #f9fafb; }
      body.auto .card { background: #1f2937; border-color: #374151; }
      body.auto .muted, body.auto .k { color: #9ca3af; }
      body.auto .pill { background: #374151; color: #f9fafb; }
    }
  </style>
</head>
<body class="auto">
  <main class="page">
    <section class="card">
      <h1><span id="city">--</span> grid CO₂ status</h1>
      <div class="muted" id="meta">Waiting for /status...</div>
      <div class="row">
        <button id="refresh">Refresh</button>
        <button id="theme" class="themeBtn">Dark mode</button>
        <span class="muted">Auto refresh every 30s</span>
      </div>
    </section>
    <section class="card">
      <div class="grid">
        <div><div class="k">Carbon intensity</div><div class="v"><span id="ci">--</span> gCO₂/kWh</div></div>
        <div><div class="k">Provider</div><div class="v" id="provider">--</div></div>
        <div><div class="k">Recommendation</div><div class="v"><span class="pill" id="verdict">--</span></div></div>
        <div><div class="k">Reason</div><div class="v" id="reason">--</div></div>
        <div><div class="k">Wait hours</div><div class="v" id="wait">--</div></div>
        <div><div class="k">Next best</div><div class="v" id="next">--</div></div>
      </div>
    </section>
  </main>
  <script>
    const els = { city:city, meta:meta, ci:ci, provider:provider, verdict:verdict, reason:reason, wait:wait, next:next, refresh:refresh, theme:theme };
    function verdictClass(v){ if(v==='GO')return 'pill ok'; if(v==='WAIT')return 'pill no'; return 'pill wait'; }
    function fill(data){ const rec=data.recommendation||{}; els.city.textContent=data.city||'--'; els.meta.textContent=`${data.cc||'--'} • ${data.datetime||'--'} • lat ${data.lat ?? '--'}, lon ${data.lon ?? '--'}`; els.ci.textContent=data.carbonIntensity ?? '--'; els.provider.textContent=data._provider||'--'; els.verdict.textContent=rec.verdict||'--'; els.verdict.className=verdictClass(rec.verdict||''); els.reason.textContent=rec.reason||'--'; els.wait.textContent=rec.wait_hours ?? '--'; els.next.textContent=rec.next_best||'--'; }
    function applyTheme(mode){
      document.body.className = mode;
      els.theme.textContent = mode === 'dark' ? 'Light mode' : 'Dark mode';
      try { localStorage.setItem('pico_theme', mode); } catch (_) {}
    }
    function initTheme(){
      let mode = 'auto';
      try { mode = localStorage.getItem('pico_theme') || 'auto'; } catch (_) {}
      if (mode !== 'dark' && mode !== 'auto') mode = 'auto';
      applyTheme(mode);
    }
    async function load(){ try{ const res=await fetch('/status',{cache:'no-store'}); if(!res.ok)throw new Error('HTTP '+res.status); fill(await res.json()); }catch(err){ els.meta.textContent='Error loading /status: '+err.message; } }
    els.refresh.addEventListener('click', load);
    els.theme.addEventListener('click', ()=>applyTheme(document.body.className === 'dark' ? 'auto' : 'dark'));
    initTheme();
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>
"""


# TODO: THIS SHOULD HANDLE CEST/BST
def set_time(offset=0, delta=2208988800, host="pool.ntp.org"):
    NTP_QUERY = bytearray(48)
    NTP_QUERY[0] = 0x1B
    addr = socket.getaddrinfo(host, 123)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1)
        s.sendto(NTP_QUERY, addr)
        msg = s.recv(48)
    finally:
        s.close()
    val = struct.unpack("!I", msg[40:44])[0]
    t = val - delta
    tm = time.gmtime(t+offset)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    log("Local time:", _now_stamp())


def handle_http_request(conn):
    if conn is None:
        return

    request = parse_request(conn)
    if not request:
        return

    method, path_qs = request
    path, params = split_path_qs(path_qs)

    try:
        process_http_request(conn, method, path, params)
    except Exception as error:
        sys.print_exception(error)
        send_json(conn, 500, {"error": "Internal error", "details": str(error)})
    finally:
        try:
            conn.close()
        except Exception:
            pass

def process_http_request(conn, method, path, params):
    if method != "GET":
        return send_json(conn, 405, {"error": "Only GET supported"})

    if path == "/":
        return send_html(conn, 200, build_index_html())
    if path == "/em/window":
        return send_json(conn, 200, handle_em_window(params))
    if path == "/em/window-overlay":
        return send_json(conn, 200, handle_em_overlay(params))
    if path == "/status":
        return send_json(conn, 200, handle_status(params))

    send_json(conn, 404, {"error": "Not found", "path": path})

def get_connection():
    if _server_socket is None:
        return None
    try:
        conn, _ = _server_socket.accept()
        return conn
    except OSError:
        return None

def open_socket(ip):
    global _server_socket

    addr = socket.getaddrinfo(CONFIG.server.host, CONFIG.server.port)[0][-1]
    _server_socket = socket.socket()
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(addr)
    _server_socket.listen(2)
    _server_socket.settimeout(1)
    log("Pico running: http://%s:%d" % (ip, CONFIG.server.port))


def serve_forever(ip):
    global _epd

    open_socket(ip)
    _epd = get_epd()

    render_placeholder_screen("BOOT", "Waiting for data...")
    while True:
        _display_tick()

        conn = get_connection()
        handle_http_request(conn)


# =========================
# Network bootstrap
# =========================

_wlan = None

def wifi_connect(timeout_ms=15000):
    global _wlan

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)

    if _wlan.isconnected():
        ip = _wlan.ifconfig()[0]
        log("WiFi: connected %s" % ip)
        return True, ip

    _wlan.connect(CONFIG.wifi.ssid, CONFIG.wifi.password)
    start = time.ticks_ms()
    while not _wlan.isconnected():
        time.sleep_ms(200)
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            log("WiFi: not connected")
            return False, ""

    ip = _wlan.ifconfig()[0]
    log("WiFi: connected %s" % ip)
    return True, ip


def wifi_ok():
    return bool(_wlan) and _wlan.isconnected()


def wifi_signal_bars():
    if not wifi_ok():
        return 0

    try:
        rssi = _wlan.status("rssi")
    except Exception:
        return 4

    if rssi is None:
        return 0

    # Typical RSSI (dBm) thresholds for 4 bars.
    if rssi >= -55:
        return 4
    if rssi >= -67:
        return 3
    if rssi >= -75:
        return 2
    if rssi >= -85:
        return 1

    return 0


# =========================
# main
# =========================

def main():
    gc.enable()
    connected, ip = wifi_connect()
    
    if not connected:
        CONFIG.wifi.ssid = "" # CHANGE ME
        CONFIG.wifi.password = "" # CHANGE ME
        connected, ip = wifi_connect()
    
    if connected:
        set_time(2) # ITALY GMT+1 # TODO: FIX DAYLIGHT
        
    serve_forever(ip)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error)
