"""UK Carbon Intensity provider for firmware."""

import time
from utils import _format_timestamp, http_get_json
from providers.base import parse_provider_history


def ukci_format_timestamp(epoch_value):
    return _format_timestamp(time.gmtime(epoch_value), include_seconds=False) + "Z"


def parse_ukci_payload(payload):
    return parse_provider_history(
        payload.get("data") or [],
        datetime_key="from",
        intensity_getter=lambda point: (point.get("intensity") or {}).get("actual") or (point.get("intensity") or {}).get("forecast"),
    )

def fetch_uk_ci_window(start_epoch, end_epoch):
    api_url = "https://api.carbonintensity.org.uk/intensity/%s/%s" % (
        ukci_format_timestamp(start_epoch),
        ukci_format_timestamp(end_epoch),
    )
    payload = http_get_json(api_url, "UKCI")
    return {"city": "Great Britain", "history": parse_ukci_payload(payload), "_provider": "uk"}
