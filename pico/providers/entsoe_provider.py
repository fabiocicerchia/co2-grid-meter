"""ENTSO-E provider adapter."""

import xml.etree.ElementTree as xml_tree
from datetime import datetime, timedelta

from requests import Session

from ..config import AppConfig
from pico.providers.base import EmissionsProvider
from pico.providers.constants import ENTSOE_DOMAIN, PSR_EMISSION_FACTOR
from pico.utils import floor_hour, iso_utc


class EntsoeProvider(EmissionsProvider):
    """Computes carbon intensity from ENTSO-E generation mix."""

    provider_name = "entsoe"

    def __init__(self, session: Session, config: AppConfig):
        self._session = session
        self._config = config

    def is_enabled(self, country_code: str) -> bool:
        mapped_country_code = (
            self._config.providers.entsoe.area_override or country_code
        )
        return bool(
            self._config.providers.entsoe.token and mapped_country_code in ENTSOE_DOMAIN
        )

    def fetch_history(self, latitude, longitude, country_code, start, end):
        del latitude, longitude
        mapped_country_code = (
            self._config.providers.entsoe.area_override or country_code
        )
        domain_id = ENTSOE_DOMAIN[mapped_country_code]

        response = self._session.get(
            self._config.providers.entsoe.base_url,
            params={
                "securityToken": self._config.providers.entsoe.token,
                "documentType": "A75",
                "processType": "A16",
                "in_Domain": domain_id,
                "periodStart": start.strftime("%Y%m%d%H%M"),
                "periodEnd": end.strftime("%Y%m%d%H%M"),
            },
            timeout=30,
        )
        response.raise_for_status()

        root = xml_tree.fromstring(response.text)
        self._strip_xml_namespaces(root)
        hourly_buckets = self._extract_hourly_buckets(root)

        history = []
        for hour_timestamp in sorted(hourly_buckets):
            total_mw = hourly_buckets[hour_timestamp]["mw"]
            if total_mw <= 0:
                continue
            carbon_intensity = hourly_buckets[hour_timestamp]["weighted"] / total_mw
            history.append(
                {
                    "datetime": iso_utc(hour_timestamp),
                    "carbonIntensity": int(round(carbon_intensity)),
                }
            )

        return {"history": history, "provider": self.provider_name}

    @staticmethod
    def _strip_xml_namespaces(root) -> None:
        for element in root.iter():
            if "}" in element.tag:
                element.tag = element.tag.split("}", 1)[1]

    @staticmethod
    def _resolution_to_interval(resolution: str) -> timedelta:
        return timedelta(hours=1) if resolution == "PT60M" else timedelta(minutes=15)

    def _extract_hourly_buckets(self, root):
        buckets = {}
        for series in root.findall(".//TimeSeries"):
            psr_type = series.find(".//MktPSRType/psrType")
            emission_factor = PSR_EMISSION_FACTOR.get(
                psr_type.text.strip()
                if psr_type is not None and psr_type.text
                else None
            )
            period = series.find(".//Period")
            if period is None:
                continue

            period_start_text = self._safe_xml_text(period, "timeInterval/start")
            resolution = self._safe_xml_text(period, "resolution")
            if not period_start_text:
                continue

            period_start = datetime.fromisoformat(
                period_start_text.replace("Z", "+00:00")
            )
            interval = self._resolution_to_interval(resolution)

            for point in period.findall("Point"):
                position_text = self._safe_xml_text(point, "position", "0")
                quantity_text = self._safe_xml_text(point, "quantity", "0")
                position = int(position_text)
                quantity_mw = float(quantity_text)
                hour = floor_hour(period_start + (position - 1) * interval)
                bucket = buckets.setdefault(hour, {"mw": 0.0, "weighted": 0.0})
                bucket["mw"] += quantity_mw
                if emission_factor is not None:
                    bucket["weighted"] += quantity_mw * emission_factor
        return buckets

    @staticmethod
    def _safe_xml_text(element, path, default=""):
        child = element.find(path)
        if child is None or child.text is None:
            return default
        return child.text.strip()
