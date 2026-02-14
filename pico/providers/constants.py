"""Provider constants and mappings used across implementations."""

WT_REGION_MAP = {
    "US": "CAISO_NORTH",
    "CA": "CAISO_NORTH",
    "IT": "IT",
    "GB": "GB",
    "UK": "GB",
    "FR": "FR",
    "DE": "DE",
    "ES": "ES",
}

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
    "B01": 12,
    "B02": 820,
    "B03": 490,
    "B04": 780,
    "B05": 900,
    "B06": 650,
    "B07": 700,
    "B08": 950,
    "B09": 20,
    "B10": 12,
    "B11": 8,
    "B12": 8,
    "B13": 12,
    "B14": 15,
    "B15": 10,
    "B16": 450,
    "B17": 700,
    "B18": 12,
    "B19": 10,
    "B20": 10,
    "B21": 45,
}
