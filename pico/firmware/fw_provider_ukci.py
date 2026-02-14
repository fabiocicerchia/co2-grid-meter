"""UK Carbon Intensity provider for firmware."""

try:
    import urequests as requests
except Exception:
    requests = None

from fw_utils import ProviderError
from pico.fw_providers_utils import parse_ukci_payload, ukci_format_timestamp


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

    history = parse_ukci_payload(payload)
    return {"city": "Great Britain", "history": history, "_provider": "uk"}
