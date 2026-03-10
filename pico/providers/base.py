from abc import ABC, abstractmethod
from datetime import datetime
from utils import safe_float


def parse_provider_history(points, datetime_key, intensity_getter):
    history = []
    for point in points:
        point_time = point.get(datetime_key)
        value = safe_float(intensity_getter(point))
        if point_time and value is not None:
            history.append({"datetime": point_time, "carbonIntensity": value})
    history.sort(key=lambda p: p["datetime"])
    return history


class EmissionsProvider(ABC):
    provider_name: str

    @abstractmethod
    def is_enabled(self, country_code: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_history(
        self,
        latitude: float,
        longitude: float,
        country_code: str,
        start: datetime,
        end: datetime,
    ) -> dict:
        raise NotImplementedError
