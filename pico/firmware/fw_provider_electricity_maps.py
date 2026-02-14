"""Electricity Maps provider for firmware."""

try:
    import urequests as requests
except Exception:
    requests = None

import fw_config
from fw_utils import ProviderError, epoch_to_iso_z
from pico.fw_providers_utils import parse_em_payload


def fetch_em_past_range(lat, lon, start_epoch, end_epoch):
    if not requests:
        raise ProviderError("urequests not available")
    if not (
        fw_config.CONFIG.providers.electricity_maps.enabled
        and fw_config.CONFIG.providers.electricity_maps.token
    ):
        raise ProviderError("Electricity Maps disabled/missing token")

    query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
        str(lat),
        str(lon),
        epoch_to_iso_z(start_epoch),
        epoch_to_iso_z(end_epoch),
    )
    api_url = (
        fw_config.CONFIG.providers.electricity_maps.base_url
        + "/v3/carbon-intensity/past-range?"
        + query
    )

    response = None
    try:
        response = requests.get(
            api_url,
            headers={"auth-token": fw_config.CONFIG.providers.electricity_maps.token},
        )
        if response.status_code != 200:
            raise ProviderError("EM HTTP %d" % response.status_code)
        payload = response.json()
    finally:
        if response:
            try:
                response.close()
            except Exception:
                pass

    history = parse_em_payload(payload)
    return {
        "city": payload.get("zone") or payload.get("city") or "ElectricityMaps",
        "history": history,
        "_provider": "em",
    }
