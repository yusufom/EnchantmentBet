from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "enchantmentbet"

    # auto | live | mock
    data_mode: str = "auto"

    # Comma-separated subset of football,basketball,tennis
    enabled_sports: str = "football"

    # Cap on fixtures predicted per sport per day. Each football fixture costs
    # ~4 API calls, so mind your api-sports plan's daily quota.
    max_fixtures: int = 40

    # SportMonks (odds, match facts). Free tier covers only the Danish
    # Superliga and Scottish Premiership.
    sportmonks_api_key: str = ""

    # How far to trust bookmaker odds over the model's own probabilities.
    # Backtested on 157 Danish/Scottish fixtures: blending improves calibration
    # monotonically (log-loss 1.0264 -> 1.0008 at full weight) but not pick
    # accuracy. 0.5 takes most of the calibration gain while keeping the
    # model's independent signal — at 1.0 it would just mirror the bookmaker.
    odds_weight: float = 0.5

    # Weight given to expected goals over actual goals when both are known.
    # xG predicts future scoring better than past goals, which carry finishing
    # luck; some actual-goal signal is kept because xG models have their own
    # error. 0 disables the xG layer entirely.
    xg_weight: float = 0.7

    # How long a cached team-stats row stays fresh. Safe to keep high on
    # limited plans, whose accessible season is already completed and static.
    stats_ttl_days: int = 7

    # Max seconds one refresh may spend waiting on api-sports rate limits
    # (free plans allow only 10 requests/minute). Teams that don't fit the
    # budget fall back to defaults and are filled in by the next refresh via
    # the 24h stats cache.
    api_budget_seconds: int = 150

    apisports_key: str = ""
    apitennis_key: str = ""
    newsapi_key: str = ""

    # Anthropic Claude layer: filters news relevance, writes per-fixture
    # analysis, and applies a small bounded adjustment to the model's odds.
    anthropic_api_key: str = ""
    # Required when the key is identity-linked: the workspace the requests
    # act in (Console -> Settings -> Workspaces, id starts with "wrkspc_").
    anthropic_workspace_id: str = ""
    llm_model: str = "claude-opus-5"
    llm_enabled: bool = True

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def enabled_sports_list(self) -> list[str]:
        return [s.strip() for s in self.enabled_sports.split(",") if s.strip()]

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
