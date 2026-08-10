from abc import ABC, abstractmethod

from ..schemas import FixtureContext


class SportProvider(ABC):
    """Fetches everything needed to predict a day's fixtures for one sport."""

    data_source: str  # "live" | "mock"

    @abstractmethod
    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        """date is YYYY-MM-DD (UTC). Returns one context per fixture."""
        raise NotImplementedError
