"""Live adapter for api-tennis.com.

Rankings drive an Elo-like rating; serve/return point rates are synthesized
from the rating gap per fixture, which the Markov model then consumes.
"""

import asyncio
import logging
import math
import time

import httpx

from ..config import Settings, get_settings
from ..schemas import Competitor, Fixture, FixtureContext, TeamStats
from .base import SportProvider
from .news import maybe_fetch_news

logger = logging.getLogger(__name__)

BASE = "https://api.api-tennis.com/tennis/"

_rankings_cache: dict[str, tuple[float, dict[str, int]]] = {}
RANKINGS_TTL = 12 * 3600


def _rating_from_rank(rank: int | None) -> float:
    if not rank or rank <= 0:
        return 1500.0
    return 1900.0 - 62.0 * math.log(rank)


class APITennisProvider(SportProvider):
    data_source = "live"

    def __init__(self, settings: Settings):
        self.key = settings.apitennis_key
        self.newsapi_key = settings.newsapi_key
        self.sem = asyncio.Semaphore(5)

    async def _get(self, client: httpx.AsyncClient, method: str, **params) -> list:
        async with self.sem:
            resp = await client.get(
                BASE, params={"method": method, "APIkey": self.key, **params}
            )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("success") != 1:
            raise RuntimeError(f"api-tennis error on {method}: {payload}")
        result = payload.get("result", [])
        return result if isinstance(result, list) else [result]

    async def _rankings(self, client: httpx.AsyncClient, tour: str) -> dict[str, int]:
        cached = _rankings_cache.get(tour)
        if cached and time.time() - cached[0] < RANKINGS_TTL:
            return cached[1]
        try:
            rows = await self._get(client, "get_standings", event_type=tour)
            ranks = {str(r["player_key"]): int(r["place"]) for r in rows if r.get("place")}
            _rankings_cache[tour] = (time.time(), ranks)
            return ranks
        except Exception:
            logger.warning("tennis rankings unavailable for %s", tour)
            return {}

    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        async with httpx.AsyncClient(timeout=25.0) as client:
            raw = await self._get(
                client, "get_fixtures", date_start=date, date_stop=date, timezone="UTC"
            )
            singles = [
                f for f in raw
                if "singles" in (f.get("event_type_type") or "").lower()
                and f.get("event_status", "") in ("", "Not Started")
            ][: get_settings().max_fixtures]
            atp = await self._rankings(client, "ATP")
            wta = await self._rankings(client, "WTA")
            ranks = {**wta, **atp}

            contexts = []
            for f in singles:
                ctx = await self._build_context(client, f, date, ranks)
                if ctx is not None:
                    contexts.append(ctx)
            return contexts

    async def _build_context(
        self, client: httpx.AsyncClient, f: dict, date: str, ranks: dict[str, int]
    ) -> FixtureContext | None:
        try:
            p1_key, p2_key = str(f.get("first_player_key")), str(f.get("second_player_key"))
            start = f"{f.get('event_date', date)}T{f.get('event_time') or '12:00'}:00Z"
            fixture = Fixture(
                id=str(f["event_key"]),
                sport="tennis",
                league=f.get("tournament_name") or "Tennis",
                start_time=start,
                home=Competitor(id=p1_key, name=f["event_first_player"]),
                away=Competitor(id=p2_key, name=f["event_second_player"]),
                round=f.get("tournament_round"),
                surface=f.get("tournament_sourface") or f.get("tournament_surface"),
                best_of=5 if "grand slam" in (f.get("event_type_type") or "").lower() else 3,
            )
            r1 = _rating_from_rank(ranks.get(p1_key))
            r2 = _rating_from_rank(ranks.get(p2_key))
            edge = max(-0.05, min(0.05, (r1 - r2) / 4000.0))
            h2h = await self._h2h(client, p1_key, p2_key)
            news = await maybe_fetch_news(
                self.newsapi_key,
                [(p1_key, f["event_first_player"]), (p2_key, f["event_second_player"])],
            )
            quality = 1.0 if (ranks.get(p1_key) and ranks.get(p2_key)) else 0.75
            return FixtureContext(
                fixture=fixture,
                home_stats=TeamStats(
                    competitor_id=p1_key, rating=r1,
                    serve_pts_won=0.62 + edge, return_pts_won=0.38 + edge,
                ),
                away_stats=TeamStats(
                    competitor_id=p2_key, rating=r2,
                    serve_pts_won=0.62 - edge, return_pts_won=0.38 - edge,
                ),
                news=news,
                h2h_home_wins=h2h[0],
                h2h_away_wins=h2h[1],
                data_quality=quality,
                source="live",
            )
        except Exception:
            logger.exception("failed to build tennis context for event %s", f.get("event_key"))
            return None

    async def _h2h(
        self, client: httpx.AsyncClient, p1: str, p2: str
    ) -> tuple[int, int]:
        try:
            rows = await self._get(
                client, "get_H2H", first_player_key=p1, second_player_key=p2
            )
            h2h = rows[0].get("H2H", []) if rows else []
            w1 = sum(1 for m in h2h if str(m.get("event_winner")) == "First Player")
            w2 = sum(1 for m in h2h if str(m.get("event_winner")) == "Second Player")
            return w1, w2
        except Exception:
            return 0, 0
