from abc import ABC, abstractmethod
from datetime import datetime


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
