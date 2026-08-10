from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "enchantmentbet"

    # auto | live | mock
    data_mode: str = "auto"

    apisports_key: str = ""
    apitennis_key: str = ""
    newsapi_key: str = ""

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def live_enabled(self, sport: str) -> bool:
        """Whether a live provider can be used for the given sport."""
        if self.data_mode == "mock":
            return False
        has_key = {
            "football": bool(self.apisports_key),
            "basketball": bool(self.apisports_key),
            "tennis": bool(self.apitennis_key),
        }.get(sport, False)
        if self.data_mode == "live" and not has_key:
            raise RuntimeError(f"DATA_MODE=live but no API key configured for {sport}")
        return has_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
