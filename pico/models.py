from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    country: str
    city: str
    source: str


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime
