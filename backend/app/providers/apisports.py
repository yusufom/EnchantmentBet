"""Live adapters for api-sports.io (API-FOOTBALL v3 and API-BASKETBALL v1).

Every sub-request degrades gracefully: if a stats/injury call fails we fall
back to league-average defaults and lower the context's data_quality instead
of failing the whole slate.
"""

import asyncio
import logging
import re
import time

import httpx

from ..config import Settings, get_settings
from ..engine.elo import rating_from_performance
from ..schemas import Competitor, Fixture, FixtureContext, Injury, TeamStats
from .base import SportProvider
from .news import maybe_fetch_news

logger = logging.getLogger(__name__)

FOOTBALL_BASE = "https://v3.football.api-sports.io"
BASKETBALL_BASE = "https://v1.basketball.api-sports.io"

# Predict these competitions, in this priority order (top leagues, their
# second divisions, the full EFL ladder, plus continental cups). When a day
# has none (off-season, breaks) fall back to whatever is on, minus
# youth/reserve/amateur competitions. IDs verified against /leagues.
FOOTBALL_LEAGUES = {
    1: "World Cup", 4: "Euro Championship", 9: "Copa America",
    2: "Champions League", 3: "Europa League", 848: "Conference League",
    # England — all four tiers + cups
    39: "Premier League", 40: "Championship", 41: "League One", 42: "League Two",
    45: "FA Cup", 48: "League Cup",
    # Top leagues + second divisions
    140: "La Liga", 141: "Segunda Division", 143: "Copa del Rey",
    135: "Serie A", 136: "Serie B",
    78: "Bundesliga", 79: "2. Bundesliga",
    61: "Ligue 1", 62: "Ligue 2",
    88: "Eredivisie", 89: "Eerste Divisie",
    94: "Primeira Liga", 95: "Segunda Liga",
    179: "Scottish Premiership", 180: "Scottish Championship",
    144: "Belgian Pro League", 145: "Challenger Pro League",
    203: "Super Lig", 204: "Turkish 1. Lig",
    71: "Serie A Brazil", 72: "Serie B Brazil",
    128: "Liga Profesional Argentina", 129: "Primera Nacional",
    # Other majors
    98: "J1 League", 103: "Eliteserien", 113: "Allsvenskan",
    207: "Swiss Super League", 253: "MLS", 262: "Liga MX",
    292: "K League 1", 307: "Saudi Pro League",
}
_LEAGUE_PRIORITY = {lid: i for i, lid in enumerate(FOOTBALL_LEAGUES)}
EXCLUDE_LEAGUE_KEYWORDS = (
    "women", "femen", "u17", "u19", "u20", "u21", "u23", "youth", "junior",
    "reserve", "amateur", "friendlies",
)
NBA_LEAGUE_ID = 12


def _fallback_ok(league_name: str) -> bool:
    lower = league_name.lower()
    return not any(k in lower for k in EXCLUDE_LEAGUE_KEYWORDS)

_stats_cache: dict[tuple, tuple[float, TeamStats]] = {}
STATS_TTL = 24 * 3600
# league_id -> season that actually returns data (free plans lag ~2 seasons)
_working_season: dict[tuple[str, int], int | str] = {}
# Season range the plan can access, parsed from api-sports plan errors
# ("Free plans do not have access to this season, try from 2022 to 2024.")
_plan_window: list[int | None] = [None, None]
_PLAN_WINDOW_RE = re.compile(r"try from (\d{4}) to (\d{4})")


def _season_allowed(year: int) -> bool:
    lo, hi = _plan_window
    return lo is None or lo <= year <= hi


def _note_plan_error(exc: Exception) -> None:
    m = _PLAN_WINDOW_RE.search(str(exc))
    if m:
        _plan_window[0], _plan_window[1] = int(m.group(1)), int(m.group(2))


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


# Below this many remaining daily requests, skip optional calls (injuries,
# H2H) and spend what's left on team stats — the strongest signal.
QUOTA_RESERVE = 25


class _APISportsBase(SportProvider):
    data_source = "live"

    def __init__(self, settings: Settings):
        self.key = settings.apisports_key
        self.newsapi_key = settings.newsapi_key
        self.sem = asyncio.Semaphore(3)
        self.quota_remaining: int | None = None
        self.minute_limit: int | None = None
        self.deadline: float | None = None

    def _client(self, base: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base, headers={"x-apisports-key": self.key}, timeout=25.0
        )

    def _quota_low(self) -> bool:
        """True when optional calls (injuries, H2H) should be skipped: daily
        quota nearly gone, or a throttled plan (<=10 req/min) where every
        request slot is better spent on team stats."""
        if self.quota_remaining is not None and self.quota_remaining < QUOTA_RESERVE:
            return True
        return self.minute_limit is not None and self.minute_limit <= 10

    def start_budget(self) -> None:
        self.deadline = time.monotonic() + get_settings().api_budget_seconds

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> list:
        """GET with per-minute rate-limit backoff (free plans allow 10/min).

        Rate-limited calls are retried with a pause until the refresh's time
        budget runs out, at which point they raise and the caller degrades.
        """
        while True:
            async with self.sem:
                resp = await client.get(path, params=params)
            remaining = resp.headers.get("x-ratelimit-requests-remaining")
            if remaining is not None:
                try:
                    self.quota_remaining = int(remaining)
                except ValueError:
                    pass
            minute_limit = resp.headers.get("x-ratelimit-limit")
            if minute_limit is not None:
                try:
                    self.minute_limit = int(minute_limit)
                except ValueError:
                    pass
            payload = resp.json() if resp.status_code in (200, 429) else None
            errors = (payload or {}).get("errors")
            error_text = str(errors or "")
            rate_limited = resp.status_code == 429 or "rateLimit" in error_text or (
                "Too many requests" in error_text
            )
            if rate_limited:
                if self.deadline is not None and time.monotonic() + 16 > self.deadline:
                    raise RuntimeError(f"api-sports rate limited on {path}, budget spent")
                await asyncio.sleep(15)
                continue
            resp.raise_for_status()
            if errors and (errors if isinstance(errors, list) else list(errors.values())):
                raise RuntimeError(f"api-sports error on {path}: {errors}")
            return payload.get("response", [])


class APISportsFootball(_APISportsBase):
    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        season = _football_season(date)
        self.start_budget()
        async with self._client(FOOTBALL_BASE) as client:
            raw = await self._get(
                client, "/fixtures", {"date": date, "timezone": "UTC"}
            )
            major = sorted(
                (f for f in raw if f["league"]["id"] in FOOTBALL_LEAGUES),
                key=lambda f: _LEAGUE_PRIORITY[f["league"]["id"]],
            )
            if not major:
                major = sorted(
                    (f for f in raw if _fallback_ok(f["league"]["name"])),
                    key=lambda f: f["league"]["id"],
                )
            raw = major[: get_settings().max_fixtures]
            # Build at most two fixtures at a time so a tight rate-limit
            # budget completes whole fixtures (both teams) in priority order
            # instead of scattering half-resolved pairs across the slate.
            build_sem = asyncio.Semaphore(2)

            async def build(f: dict) -> FixtureContext | None:
                async with build_sem:
                    return await self._build_context(client, f, season, date)

            contexts = await asyncio.gather(*(build(f) for f in raw))
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
            if self._quota_low():
                injuries, h2h = [], (0, 0, 0)
            else:
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

    async def get_results(self, date: str) -> dict[str, dict]:
        """One /fixtures call: final scores for the date's finished games."""
        self.start_budget()
        finished = {"FT", "AET", "PEN"}
        async with self._client(FOOTBALL_BASE) as client:
            raw = await self._get(client, "/fixtures", {"date": date, "timezone": "UTC"})
        results = {}
        for f in raw:
            status = ((f["fixture"].get("status") or {}).get("short")) or ""
            gh, ga = f["goals"]["home"], f["goals"]["away"]
            if status in finished and gh is not None and ga is not None:
                ht = (f.get("score") or {}).get("halftime") or {}
                results[str(f["fixture"]["id"])] = {
                    "home": int(gh), "away": int(ga), "status": status,
                    "ht_home": ht.get("home"), "ht_away": ht.get("away"),
                }
        return results

    async def _team_stats(
        self, client: httpx.AsyncClient, team_id: int, league_id: int, season: int
    ) -> tuple[TeamStats, float]:
        """Stats are league-scoped, so a promoted/relegated team has no rows
        for its current league in the seasons a limited plan can access. Try
        the fixture's (league, season) first; on failure resolve the team's
        real league history and query the newest accessible pair."""
        cache_key = ("football", team_id)
        cached = _stats_cache.get(cache_key)
        if cached and time.time() - cached[0] < STATS_TTL:
            return cached[1], 1.0
        season = int(season)

        # Requested pair first: one call, succeeds on plans with current data.
        if _season_allowed(season):
            stats = await self._try_stats(client, team_id, league_id, season)
            if stats:
                _stats_cache[cache_key] = (time.time(), stats)
                return stats, 1.0

        # Fallback: the team's real league history, newest accessible first.
        pairs: list[tuple[int, int]] = []
        try:
            history = await self._get(client, "/leagues", {"team": team_id, "type": "league"})
            pairs = sorted(
                (
                    (entry["league"]["id"], s["year"])
                    for entry in history
                    for s in entry.get("seasons", [])
                    if _season_allowed(s["year"]) and s["year"] <= season
                ),
                key=lambda p: p[1],
                reverse=True,
            )
        except Exception:
            pass
        for cand_league, cand_season in [p for p in pairs if p != (league_id, season)][:2]:
            stats = await self._try_stats(client, team_id, cand_league, cand_season)
            if stats:
                _stats_cache[cache_key] = (time.time(), stats)
                return stats, 0.85
        logger.warning("football stats unavailable for team %s, using defaults", team_id)
        return TeamStats(competitor_id=str(team_id)), 0.7

    async def _try_stats(
        self, client: httpx.AsyncClient, team_id: int, league_id: int, season: int
    ) -> TeamStats | None:
        try:
            rows = await self._get(
                client,
                "/teams/statistics",
                {"team": team_id, "league": league_id, "season": season},
            )
            s = rows if isinstance(rows, dict) else rows[0] if rows else {}
            played = int(s["fixtures"]["played"]["total"] or 0)
            if not played:
                return None
            wins = int(s["fixtures"]["wins"]["total"] or 0)
            scored = float(s["goals"]["for"]["average"]["total"] or 1.35)
            conceded = float(s["goals"]["against"]["average"]["total"] or 1.35)
            form_str = (s.get("form") or "")[-5:]
            return TeamStats(
                competitor_id=str(team_id),
                rating=rating_from_performance(
                    wins / played, scored - conceded, 90.0, played
                ),
                matches_played=played,
                form=list(reversed(form_str)),
                goals_scored_pg=scored,
                goals_conceded_pg=conceded,
            )
        except Exception as exc:
            _note_plan_error(exc)
            return None

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
        self.start_budget()
        async with self._client(BASKETBALL_BASE) as client:
            raw = await self._get(client, "/games", {"date": date, "timezone": "UTC"})
            nba = [g for g in raw if g["league"]["id"] == NBA_LEAGUE_ID]
            if not nba:
                nba = sorted(
                    (g for g in raw if _fallback_ok(g["league"]["name"])),
                    key=lambda g: g["league"]["id"],
                )
            raw = nba[: get_settings().max_fixtures]
            build_sem = asyncio.Semaphore(2)

            async def build(g: dict) -> FixtureContext | None:
                async with build_sem:
                    return await self._build_context(client, g, season)

            contexts = await asyncio.gather(*(build(g) for g in raw))
        return [c for c in contexts if c is not None]

    async def get_results(self, date: str) -> dict[str, dict]:
        """One /games call: final scores for the date's finished games."""
        self.start_budget()
        finished = {"FT", "AOT"}
        async with self._client(BASKETBALL_BASE) as client:
            raw = await self._get(client, "/games", {"date": date, "timezone": "UTC"})

        def half(side: dict) -> int | None:
            q1, q2 = side.get("quarter_1"), side.get("quarter_2")
            return int(q1) + int(q2) if q1 is not None and q2 is not None else None

        results = {}
        for g in raw:
            status = ((g.get("status") or {}).get("short")) or ""
            scores = g.get("scores") or {}
            home, away = scores.get("home") or {}, scores.get("away") or {}
            if status in finished and home.get("total") is not None and away.get("total") is not None:
                results[str(g["id"])] = {
                    "home": int(home["total"]), "away": int(away["total"]),
                    "status": status,
                    "ht_home": half(home), "ht_away": half(away),
                }
        return results

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
