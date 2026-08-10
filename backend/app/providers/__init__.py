from ..config import Settings
from ..schemas import Sport
from .base import SportProvider


def get_provider(sport: Sport, settings: Settings) -> SportProvider:
    if settings.live_enabled(sport):
        if sport == "football":
            from .apisports import APISportsFootball

            return APISportsFootball(settings)
        if sport == "basketball":
            from .apisports import APISportsBasketball

            return APISportsBasketball(settings)
        from .apitennis import APITennisProvider

        return APITennisProvider(settings)

    from .mock import MockProvider

    return MockProvider(sport)
