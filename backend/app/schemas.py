from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Sport = Literal["football", "basketball", "tennis"]
SPORTS: list[Sport] = ["football", "basketball", "tennis"]


class Competitor(BaseModel):
    """A team, or a player for tennis."""

    id: str
    name: str
    logo: str | None = None


class Fixture(BaseModel):
    id: str
    sport: Sport
    league: str
    country: str | None = None
    start_time: datetime | None = None
    home: Competitor
    away: Competitor
    venue: str | None = None
    round: str | None = None
    # Tennis only
    surface: str | None = None
    best_of: int | None = None


class TeamStats(BaseModel):
    """Normalized strength profile for one competitor.

    Football uses goals_*; basketball uses ratings/pace; tennis uses
    serve/return point win rates. `rating` is an Elo-like number around 1500
    derived from season performance when a true Elo is unavailable.
    """

    competitor_id: str
    rating: float = 1500.0
    matches_played: int = 0
    form: list[str] = Field(default_factory=list)  # most recent first, e.g. ["W","L","D"]

    # Football (per game)
    goals_scored_pg: float | None = None
    goals_conceded_pg: float | None = None
    goals_scored_home_pg: float | None = None
    goals_scored_away_pg: float | None = None

    # Basketball (per 100 possessions / per game)
    off_rating: float | None = None
    def_rating: float | None = None
    pace: float | None = None

    # Tennis (fraction of points won)
    serve_pts_won: float | None = None
    return_pts_won: float | None = None


class Injury(BaseModel):
    player: str
    team_id: str
    status: str  # "out" | "doubtful" | "questionable"
    detail: str | None = None
    # 0..1 — how much of the team's strength this player represents
    importance: float = 0.03


class NewsItem(BaseModel):
    team_id: str
    headline: str
    source: str | None = None
    published_at: datetime | None = None
    sentiment: float = 0.0  # -1..1


class FixtureContext(BaseModel):
    """Everything the engine needs to predict one fixture."""

    fixture: Fixture
    home_stats: TeamStats
    away_stats: TeamStats
    injuries: list[Injury] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    h2h_home_wins: int = 0
    h2h_away_wins: int = 0
    h2h_draws: int = 0
    data_quality: float = 1.0  # 0..1, discounts confidence when inputs are thin
    source: Literal["live", "mock"] = "mock"


class Market(BaseModel):
    name: str  # e.g. "match_winner", "over_under_2.5", "btts"
    outcomes: dict[str, float]  # outcome -> probability, sums to ~1
    pick: str
    pick_probability: float


class Factor(BaseModel):
    label: str
    detail: str
    impact: Literal["positive_home", "positive_away", "neutral"] = "neutral"


class AIPrediction(BaseModel):
    """Claude's own picks, independent of the statistical model.

    picks maps market -> pick, e.g. {"winner": "1", "double_chance": "1X",
    "over_under_1.5": "over", "over_under_2.5": "under", "btts": "no",
    "first_half_winner": "X", "total_points": "over"}.
    """

    picks: dict[str, str]
    confidence: float  # 0..1
    analysis: str
    model: str


class FixtureResult(BaseModel):
    home_score: int
    away_score: int
    status: str  # e.g. "FT", "AET"
    outcome: Literal["home", "draw", "away"]
    ht_home: int | None = None  # half-time score when the provider has it
    ht_away: int | None = None
    fetched_at: datetime


class MarketGrade(BaseModel):
    market: str
    pick: str
    actual: str
    correct: bool


class Prediction(BaseModel):
    sport: Sport
    date: str  # YYYY-MM-DD (UTC date of the fixture)
    fixture_id: str
    fixture: Fixture
    markets: list[Market]
    predicted_score: str | None = None
    expected_home: float | None = None
    expected_away: float | None = None
    confidence: float  # 0..1
    confidence_label: Literal["low", "medium", "high"]
    factors: list[Factor] = Field(default_factory=list)
    injuries: list[Injury] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    insight: str | None = None  # Claude's short written analysis
    ai: AIPrediction | None = None  # Claude's own market picks
    algorithm: str
    data_source: Literal["live", "mock"]
    generated_at: datetime
    result: FixtureResult | None = None
    grades: list[MarketGrade] = Field(default_factory=list)
    ai_grades: list[MarketGrade] = Field(default_factory=list)
    pick_correct: bool | None = None


class AccuracySummary(BaseModel):
    date: str
    graded: int
    total: int
    pick_accuracy: float | None = None  # 0..1 over graded fixtures
    market_accuracy: dict[str, float] = Field(default_factory=dict)
    exact_score_accuracy: float | None = None
    ai_overall: float | None = None  # all AI picks pooled
    ai_accuracy: dict[str, float] = Field(default_factory=dict)  # per AI market


class RefreshMeta(BaseModel):
    sport: Sport
    date: str
    refreshed_at: datetime
    fixtures: int
    data_source: Literal["live", "mock"]


class PredictionsResponse(BaseModel):
    date: str
    sport: str
    predictions: list[Prediction]
    meta: list[RefreshMeta] = Field(default_factory=list)
    accuracy: AccuracySummary | None = None
    errors: list[str] = Field(default_factory=list)


class RefreshRequest(BaseModel):
    date: str
    sport: Sport | None = None  # None -> refresh all sports for that date
