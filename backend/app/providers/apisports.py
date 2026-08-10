"""Live adapters for api-sports.io (API-FOOTBALL v3 and API-BASKETBALL v1).

Every sub-request degrades gracefully: if a stats/injury call fails we fall
back to league-average defaults and lower the context's data_quality instead
of failing the whole slate.
"""

import asyncio
import logging
import time

import httpx

from ..config import Settings
from ..engine.elo import rating_from_performance
from ..schemas import Competitor, Fixture, FixtureContext, Injury, TeamStats
from .base import SportProvider
from .news import maybe_fetch_news

logger = logging.getLogger(__name__)

FOOTBALL_BASE = "https://v3.football.api-sports.io"
BASKETBALL_BASE = "https://v1.basketball.api-sports.io"

# Predict major competitions first; when a day has none (off-season, breaks)
# fall back to whatever is on, minus youth/reserve/amateur competitions.
FOOTBALL_LEAGUES = {
    1: "World Cup", 2: "Champions League", 3: "Europa League", 4: "Euro Championship",
    9: "Copa America", 39: "Premier League", 40: "Championship", 45: "FA Cup",
    61: "Ligue 1", 71: "Serie A Brazil", 78: "Bundesliga", 88: "Eredivisie",
    94: "Primeira Liga", 98: "J1 League", 103: "Eliteserien", 113: "Allsvenskan",
    128: "Liga Profesional Argentina", 135: "Serie A", 140: "La Liga",
    143: "Copa del Rey", 144: "Belgian Pro League", 179: "Scottish Premiership",
    203: "Super Lig", 207: "Swiss Super League", 253: "MLS", 262: "Liga MX",
    292: "K League 1", 307: "Saudi Pro League", 848: "Conference League",
}
EXCLUDE_LEAGUE_KEYWORDS = (
    "women", "femen", "u17", "u19", "u20", "u21", "u23", "youth", "junior",
    "reserve", "amateur", "friendlies",
)
NBA_LEAGUE_ID = 12
MAX_FIXTURES = 15


def _fallback_ok(league_name: str) -> bool:
    lower = league_name.lower()
    return not any(k in lower for k in EXCLUDE_LEAGUE_KEYWORDS)

_stats_cache: dict[tuple, tuple[float, TeamStats]] = {}
STATS_TTL = 6 * 3600
# league_id -> season that actually returns data (free plans lag ~2 seasons)
_working_season: dict[tuple[str, int], int | str] = {}


def _football_season(date: str) -> int:
    year, month = int(date[:4]), int(date[5:7])
    return year if month >= 7 else year - 1


def _basketball_season(date: str) -> str:
    year, month = int(date[:4]), int(date[5:7])
    start = year if month >= 10 else year - 1
    return f"{start}-{start + 1}"


def _previous_seasons(season: str, count: int = 3) -> list[str]:
    """"2025-2026" -> ["2024-2025", …]; "2026" -> ["2025", …]."""
    out = []
    for i in range(1, count + 1):
        if "-" in season:
            start = int(season.split("-")[0]) - i
            out.append(f"{start}-{start + 1}")
        else:
            out.append(str(int(season) - i))
    return out


class _APISportsBase(SportProvider):
    data_source = "live"

    def __init__(self, settings: Settings):
        self.key = settings.apisports_key
        self.newsapi_key = settings.newsapi_key
        self.sem = asyncio.Semaphore(5)

    def _client(self, base: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base, headers={"x-apisports-key": self.key}, timeout=25.0
        )

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> list:
        async with self.sem:
            resp = await client.get(path, params=params)
        resp.raise_for_status()
        payload = resp.json()
        errors = payload.get("errors")
        if errors and (errors if isinstance(errors, list) else list(errors.values())):
            raise RuntimeError(f"api-sports error on {path}: {errors}")
        return payload.get("response", [])


class APISportsFootball(_APISportsBase):
    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        season = _football_season(date)
        async with self._client(FOOTBALL_BASE) as client:
            raw = await self._get(
                client, "/fixtures", {"date": date, "timezone": "UTC"}
            )
            major = [f for f in raw if f["league"]["id"] in FOOTBALL_LEAGUES]
            if not major:
                major = sorted(
                    (f for f in raw if _fallback_ok(f["league"]["name"])),
                    key=lambda f: f["league"]["id"],
                )
            raw = major[:MAX_FIXTURES]
            contexts = await asyncio.gather(
                *(self._build_context(client, f, season, date) for f in raw)
            )
        return [c for c in contexts if c is not None]

    async def _build_context(
        self, client: httpx.AsyncClient, f: dict, season: int, date: str
    ) -> FixtureContext | None:
        try:
            fx = f["fixture"]
            league = f["league"]
            home, away = f["teams"]["home"], f["teams"]["away"]
            fixture = Fixture(
                id=str(fx["id"]),
                sport="football",
                league=league["name"],
                country=league.get("country"),
                start_time=fx.get("date"),
                home=Competitor(id=str(home["id"]), name=home["name"], logo=home.get("logo")),
                away=Competitor(id=str(away["id"]), name=away["name"], logo=away.get("logo")),
                venue=(fx.get("venue") or {}).get("name"),
                round=league.get("round"),
            )
            quality = 1.0
            season = league.get("season") or season
            home_stats, q1 = await self._team_stats(client, home["id"], league["id"], season)
            away_stats, q2 = await self._team_stats(client, away["id"], league["id"], season)
            quality = min(quality, q1, q2)
            injuries = await self._injuries(client, fx["id"])
            h2h = await self._h2h(client, home["id"], away["id"])
            news = await maybe_fetch_news(
                self.newsapi_key,
                [(str(home["id"]), home["name"]), (str(away["id"]), away["name"])],
            )
            return FixtureContext(
                fixture=fixture,
                home_stats=home_stats,
                away_stats=away_stats,
                injuries=injuries,
                news=news,
                h2h_home_wins=h2h[0],
                h2h_away_wins=h2h[1],
                h2h_draws=h2h[2],
                data_quality=quality,
                source="live",
            )
        except Exception:
            logger.exception("failed to build football context for fixture %s", f)
            return None

    async def _team_stats(
        self, client: httpx.AsyncClient, team_id: int, league_id: int, season: int
    ) -> tuple[TeamStats, float]:
        cache_key = ("football", team_id, league_id)
        cached = _stats_cache.get(cache_key)
        if cached and time.time() - cached[0] < STATS_TTL:
            return cached[1], 1.0
        # Free plans only expose stats a couple of seasons back — walk from
        # the requested season toward the free window and remember what works.
        season = int(season)
        preferred = _working_season.get(("football", league_id))
        candidates = [preferred] if preferred else []
        candidates += [s for s in (season, 2024, 2023, 2022) if s not in candidates]
        for candidate in candidates:
            try:
                rows = await self._get(
                    client,
                    "/teams/statistics",
                    {"team": team_id, "league": league_id, "season": candidate},
                )
                s = rows if isinstance(rows, dict) else rows[0] if rows else {}
                played = int(s["fixtures"]["played"]["total"] or 0)
                if not played:
                    continue
                wins = int(s["fixtures"]["wins"]["total"] or 0)
                scored = float(s["goals"]["for"]["average"]["total"] or 1.35)
                conceded = float(s["goals"]["against"]["average"]["total"] or 1.35)
                form_str = (s.get("form") or "")[-5:]
                stats = TeamStats(
                    competitor_id=str(team_id),
                    rating=rating_from_performance(
                        wins / played, scored - conceded, 90.0, played
                    ),
                    matches_played=played,
                    form=list(reversed(form_str)),
                    goals_scored_pg=scored,
                    goals_conceded_pg=conceded,
                )
                _working_season[("football", league_id)] = candidate
                _stats_cache[cache_key] = (time.time(), stats)
                return stats, 1.0 if candidate == season else 0.85
            except Exception:
                continue
        logger.warning("football stats unavailable for team %s, using defaults", team_id)
        return TeamStats(competitor_id=str(team_id)), 0.7

    async def _injuries(self, client: httpx.AsyncClient, fixture_id: int) -> list[Injury]:
        try:
            rows = await self._get(client, "/injuries", {"fixture": fixture_id})
            out = []
            for r in rows[:12]:
                reason = (r["player"].get("reason") or "").lower()
                status = "doubtful" if "doubt" in reason or "question" in reason else "out"
                out.append(
                    Injury(
                        player=r["player"]["name"],
                        team_id=str(r["team"]["id"]),
                        status=status,
                        detail=r["player"].get("reason"),
                        importance=0.04,
                    )
                )
            return out
        except Exception:
            return []

    async def _h2h(
        self, client: httpx.AsyncClient, home_id: int, away_id: int
    ) -> tuple[int, int, int]:
        try:
            # "last" is a paid-plan parameter; fetch all and slice locally.
            rows = await self._get(
                client, "/fixtures/headtohead", {"h2h": f"{home_id}-{away_id}"}
            )
            rows = sorted(rows, key=lambda r: r["fixture"]["date"], reverse=True)[:10]
            hw = aw = d = 0
            for r in rows:
                gh, ga = r["goals"]["home"], r["goals"]["away"]
                if gh is None or ga is None:
                    continue
                winner_id = (
                    r["teams"]["home"]["id"] if gh > ga else r["teams"]["away"]["id"]
                ) if gh != ga else None
                if winner_id is None:
                    d += 1
                elif winner_id == home_id:
                    hw += 1
                else:
                    aw += 1
            return hw, aw, d
        except Exception:
            return 0, 0, 0


class APISportsBasketball(_APISportsBase):
    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        season = _basketball_season(date)
        async with self._client(BASKETBALL_BASE) as client:
            raw = await self._get(client, "/games", {"date": date, "timezone": "UTC"})
            nba = [g for g in raw if g["league"]["id"] == NBA_LEAGUE_ID]
            if not nba:
                nba = sorted(
                    (g for g in raw if _fallback_ok(g["league"]["name"])),
                    key=lambda g: g["league"]["id"],
                )
            raw = nba[:MAX_FIXTURES]
            contexts = await asyncio.gather(
                *(self._build_context(client, g, season) for g in raw)
            )
        return [c for c in contexts if c is not None]

    async def _build_context(
        self, client: httpx.AsyncClient, g: dict, season: str
    ) -> FixtureContext | None:
        try:
            home, away = g["teams"]["home"], g["teams"]["away"]
            fixture = Fixture(
                id=str(g["id"]),
                sport="basketball",
                league=g["league"]["name"],
                country=(g.get("country") or {}).get("name"),
                start_time=g.get("date"),
                home=Competitor(id=str(home["id"]), name=home["name"], logo=home.get("logo")),
                away=Competitor(id=str(away["id"]), name=away["name"], logo=away.get("logo")),
            )
            league_id = g["league"]["id"]
            season = g["league"].get("season") or season
            home_stats, q1 = await self._team_stats(client, home["id"], league_id, season)
            away_stats, q2 = await self._team_stats(client, away["id"], league_id, season)
            news = await maybe_fetch_news(
                self.newsapi_key,
                [(str(home["id"]), home["name"]), (str(away["id"]), away["name"])],
            )
            return FixtureContext(
                fixture=fixture,
                home_stats=home_stats,
                away_stats=away_stats,
                news=news,
                data_quality=min(q1, q2),
                source="live",
            )
        except Exception:
            logger.exception("failed to build basketball context for game %s", g)
            return None

    async def _team_stats(
        self, client: httpx.AsyncClient, team_id: int, league_id: int, season: str
    ) -> tuple[TeamStats, float]:
        cache_key = ("basketball", team_id, league_id)
        cached = _stats_cache.get(cache_key)
        if cached and time.time() - cached[0] < STATS_TTL:
            return cached[1], 1.0
        season = str(season)
        preferred = _working_season.get(("basketball", league_id))
        candidates = [preferred] if preferred else []
        candidates += [s for s in [season, *_previous_seasons(season)] if s not in candidates]
        for candidate in candidates:
            try:
                s = await self._get(
                    client,
                    "/statistics",
                    {"league": league_id, "season": candidate, "team": team_id},
                )
                games = int(s["games"]["played"]["all"] or 0)
                if not games:
                    continue
                wins = int(s["games"]["wins"]["all"]["total"] or 0)
                pts_for = float(s["points"]["for"]["average"]["all"] or 112.0)
                pts_against = float(s["points"]["against"]["average"]["all"] or 112.0)
                stats = TeamStats(
                    competitor_id=str(team_id),
                    rating=rating_from_performance(
                        wins / games, pts_for - pts_against, 28.0, games
                    ),
                    matches_played=games,
                    off_rating=pts_for * 100.0 / 99.0,
                    def_rating=pts_against * 100.0 / 99.0,
                    pace=99.0,
                )
                _working_season[("basketball", league_id)] = candidate
                _stats_cache[cache_key] = (time.time(), stats)
                return stats, 1.0 if candidate == season else 0.85
            except Exception:
                continue
        logger.warning("basketball stats unavailable for team %s, using defaults", team_id)
        return TeamStats(competitor_id=str(team_id)), 0.7
