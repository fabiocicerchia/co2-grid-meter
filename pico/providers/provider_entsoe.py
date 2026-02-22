import time
import urequests
import xmltok
import io

from pico.utils import ProviderError, close_response, epoch_to_iso_z, floor_hour_epoch, iso_z_to_epoch, log
from pico.providers import TextStream, _resolution_to_seconds, _to_str, urlencode_simple


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

def entsoe_period_timestamp(epoch_value):
    year, month, day, hour, minute, *_ = time.gmtime(epoch_value)
    return "%04d%02d%02d%02d%02d" % (year, month, day, hour, minute)


def fetch_entsoe_window(country_code, start_epoch, end_epoch):
    global CONFIG
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
        response = urequests.get(url)
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
