import time

import urequests
from utils import (
    ProviderError,
    _resolution_to_seconds,
    _to_str,
    close_response,
    epoch_to_iso_z,
    floor_hour_epoch,
    iso_z_to_epoch,
    log,
    urlencode_simple,
)

from config import CONFIG
from providers.base import EmissionsProvider
from providers.entsoe_parse import iter_series

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
    "IT-NORTH": "10Y1001A1001A73I",  # IT1
    "IT-CNORTH": "10Y1001A1001A70O",  # IT2
    "IT-CSOUTH": "10Y1001A1001A71M",  # IT3
    "IT-SOUTH": "10Y1001A1001A788",  # IT4
    "IT-SARDINIA": "10Y1001A1001A74G",  # IT5
    "IT-SICILY": "10Y1001A1001A75E",  # IT6
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
    # Fossil fuels (kgCO2/MWh)
    "B01": 1050,  # Lignite
    "B02": 850,  # Hard coal
    "B03": 750,  # Coal-derived gas
    "B04": 370,  # Natural gas (avg CCGT)
    "B05": 720,  # Oil
    "B06": 1060,  # Peat
    "B07": 1100,  # Oil shale
    "B08": 700,  # Fossil mixed
    "B09": 700,  # Fossil other
    # Renewables & nuclear (operational emissions ~0)
    "B10": 0,  # Hydro run-of-river
    "B11": 0,  # Hydro reservoir
    "B12": 0,  # Hydro pumped storage
    "B13": 0,  # Marine
    "B14": 0,  # Nuclear
    "B15": 0,  # Wind offshore
    "B16": 0,  # Solar
    "B17": 0,  # Wind onshore
    "B18": 0,  # Geothermal
    "B19": 0,  # Biomass (policy zero)
    "B20": 450,  # Waste (mixed fossil fraction)
    # Other categories
    "B21": 0,  # Other renewable
    "B22": 500,  # Other
    "B23": 0,  # Energy storage (depends on charging mix)
    "B24": 0,  # Demand response
    "B25": 500,  # Mixed generation (assumed)
}


def _fill_range(
    buckets, period_start_epoch, interval_sec, start_pos, end_pos, mw, emission
):
    """Fill hourly buckets for positions [start_pos, end_pos) with a constant mw value
    (A03 step-curve fill: the last known point holds until the next one)."""
    if mw <= 0:
        return
    for p in range(start_pos, end_pos):
        point_epoch = period_start_epoch + (p - 1) * interval_sec
        hour_epoch = floor_hour_epoch(point_epoch)
        bucket = buckets.setdefault(hour_epoch, {"mw": 0.0, "weighted": 0.0})
        bucket["mw"] += mw
        if emission is not None:
            bucket["weighted"] += mw * emission


class EntsoeProvider(EmissionsProvider):
    provider_name = "entsoe"

    def is_enabled(self, country_code: str) -> bool:
        return CONFIG.providers.entsoe.enabled

    def period_timestamp(self, epoch_value):
        year, month, day, hour, minute, *_ = time.gmtime(epoch_value)
        return "%04d%02d%02d%02d%02d" % (year, month, day, hour, minute)

    def fetch_history(self, latitude, longitude, country_code, start, end):
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
            "periodStart": self.period_timestamp(start),
            "periodEnd": self.period_timestamp(end),
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

            # One pass over the six fields this actually reads, rather than
            # tokenising every tag in a document that is 95% <Point>. See
            # pico/providers/entsoe_parse.py for what that gives up.
            #
            # Streamed off the socket, not read into a string first: a 60-hour
            # window over a PT15M zone is a 180-250 KB response and the board
            # has 264 KB of SRAM in total. Each series is folded into the
            # hourly buckets below and dropped, so the peak is one read window
            # plus one series rather than the document plus a tree of it.
            log("Processing data")
            source = getattr(response, "raw", None)
            if not (source and hasattr(source, "read")):
                source = getattr(response, "content", b"") or getattr(
                    response, "text", ""
                )
            for series in iter_series(source):
                emission = PSR_EMISSION_FACTOR.get(series["psr"])
                for period in series["periods"]:
                    period_start_epoch = iso_z_to_epoch(period["start"])
                    period_end_epoch = iso_z_to_epoch(period["end"])
                    if period_start_epoch is None:
                        continue
                    interval_sec = _resolution_to_seconds(period["resolution"]) or 3600
                    total_positions = None
                    if period_end_epoch is not None and interval_sec:
                        total_positions = int(
                            (period_end_epoch - period_start_epoch) / interval_sec
                        )

                    # A03 step curve: each point holds until the next one, and
                    # the last holds to the end of the period.
                    last_position = None
                    last_quantity = None
                    for position, quantity in period["points"]:
                        if last_position is not None and last_quantity is not None:
                            _fill_range(
                                buckets,
                                period_start_epoch,
                                interval_sec,
                                last_position,
                                position,
                                last_quantity,
                                emission,
                            )
                        last_position = position
                        last_quantity = quantity

                    if (
                        last_position is not None
                        and last_quantity is not None
                        and total_positions is not None
                    ):
                        _fill_range(
                            buckets,
                            period_start_epoch,
                            interval_sec,
                            last_position,
                            total_positions + 1,
                            last_quantity,
                            emission,
                        )

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
            history.append(
                {
                    "datetime": epoch_to_iso_z(hour_epoch),
                    "carbonIntensity": int(round(intensity)),
                }
            )

        log("Processing data done")

        return {"city": mapped_country, "history": history, "_provider": "entsoe"}
