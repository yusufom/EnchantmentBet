"""Team news via newsapi.org with lightweight keyword sentiment.

Optional: returns [] when no key is configured. Sentiment feeds a small,
capped adjustment in the engine — headlines can nudge a prediction, never
dominate it.
"""

import asyncio
import logging

import httpx

from ..schemas import NewsItem

logger = logging.getLogger(__name__)

POSITIVE = {
    "returns", "return", "boost", "boosted", "fit", "back in training", "cleared",
    "available", "streak", "wins", "victory", "unbeaten", "strengthened", "in form",
}
NEGATIVE = {
    "injury", "injured", "out for", "ruled out", "doubt", "doubtful", "sidelined",
    "suspended", "ban", "banned", "crisis", "sacked", "blow", "setback", "surgery",
    "withdraws", "retired hurt", "illness", "loses", "slump",
}

_news_cache: dict[str, list[NewsItem]] = {}


def score_sentiment(text: str) -> float:
    lower = text.lower()
    pos = sum(1 for w in POSITIVE if w in lower)
    neg = sum(1 for w in NEGATIVE if w in lower)
    if pos == neg:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(pos + neg, 1)))


async def maybe_fetch_news(
    api_key: str, teams: list[tuple[str, str]]
) -> list[NewsItem]:
    """teams: list of (team_id, team_name). Returns [] without a key."""
    if not api_key:
        return []
    results = await asyncio.gather(
        *(_fetch_team(api_key, team_id, name) for team_id, name in teams)
    )
    return [item for sub in results for item in sub]


async def _fetch_team(api_key: str, team_id: str, name: str) -> list[NewsItem]:
    if team_id in _news_cache:
        return _news_cache[team_id]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f'"{name}"',
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                },
                headers={"X-Api-Key": api_key},
            )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        items = [
            NewsItem(
                team_id=team_id,
                headline=a["title"],
                source=(a.get("source") or {}).get("name"),
                published_at=a.get("publishedAt"),
                sentiment=score_sentiment(f"{a.get('title', '')} {a.get('description') or ''}"),
            )
            for a in articles
            if a.get("title")
        ]
        _news_cache[team_id] = items
        return items
    except Exception:
        logger.warning("news fetch failed for %s", name)
        return []
