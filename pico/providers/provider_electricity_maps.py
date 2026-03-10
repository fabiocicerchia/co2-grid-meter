"""Electricity Maps provider for firmware."""

from utils import ProviderError, http_get_json, epoch_to_iso_z
from providers.base import parse_provider_history
from config import CONFIG


def parse_em_payload(payload):
    return parse_provider_history(
        payload.get("history") or payload.get("data") or [],
        datetime_key="datetime",
        intensity_getter=lambda point: point.get("carbonIntensity"),
    )


def fetch_em_past_range(lat, lon, start_epoch, end_epoch):
    if not (
        CONFIG.providers.electricity_maps.enabled
        and CONFIG.providers.electricity_maps.token
    ):
        raise ProviderError("Electricity Maps disabled/missing token")

    query = "lat=%s&lon=%s&start=%s&end=%s&temporalGranularity=hourly" % (
        str(lat),
        str(lon),
        epoch_to_iso_z(start_epoch),
        epoch_to_iso_z(end_epoch),
    )
    api_url = (
        CONFIG.providers.electricity_maps.base_url
        + "/v3/carbon-intensity/past-range?"
        + query
    )

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
