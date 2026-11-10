"""Persistent team-stats cache.

Team strength profiles are expensive to fetch on rate-limited plans, so they
are cached in MongoDB rather than in process memory: coverage then accumulates
across refreshes, restarts and days instead of being re-paid every time.
"""

import logging
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..db import get_db
from ..schemas import TeamStats

logger = logging.getLogger(__name__)

# Quality scores by provenance, used as the context's data_quality.
QUALITY = {"standings": 1.0, "team_statistics": 1.0, "stale": 0.85, "prior": 0.45}


async def load_cached(sport: str, team_ids: set[str]) -> dict[str, tuple[TeamStats, float]]:
    """Fresh cached stats for the given teams, keyed by team id."""
    if not team_ids:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().stats_ttl_days)
    try:
        docs = await get_db().team_stats.find({
            "sport": sport,
            "team_id": {"$in": list(team_ids)},
            "fetched_at": {"$gte": cutoff},
        }).to_list(length=len(team_ids))
    except Exception:
        logger.warning("team stats cache unavailable, falling back to live fetches")
        return {}
    out: dict[str, tuple[TeamStats, float]] = {}
    for doc in docs:
        try:
            quality = QUALITY.get(doc.get("source", "standings"), 0.85)
            out[doc["team_id"]] = (TeamStats(**doc["stats"]), quality)
        except Exception:
            continue
    return out


async def store(sport: str, stats: TeamStats, source: str, season: str | int) -> None:
    try:
        await get_db().team_stats.update_one(
            {"sport": sport, "team_id": stats.competitor_id},
            {"$set": {
                "sport": sport,
                "team_id": stats.competitor_id,
                "stats": stats.model_dump(mode="json"),
                "source": source,
                "season": str(season),
                "fetched_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except Exception:
        logger.warning("could not cache stats for team %s", stats.competitor_id)


async def store_many(sport: str, rows: list[TeamStats], source: str, season: str | int) -> None:
    for stats in rows:
        await store(sport, stats, source, season)
