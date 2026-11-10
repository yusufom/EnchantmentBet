"""Understat expected-goals (xG) enrichment.

xG measures the quality of chances a team created and conceded, and it
predicts future results better than actual goals do — actual scorelines carry
a lot of finishing luck that does not repeat. The Dixon-Coles model here is
driven by scoring rates, so feeding it xG-blended rates makes it forecast the
team rather than the last few bounces of the ball.

Coverage is the big-5 leagues only. Everything else keeps using actual goals.

Source: understat.com's own league endpoint (the same JSON its table loads
from). External content, so every field is validated before use.
"""

import logging
import re
import time
import unicodedata

import httpx

logger = logging.getLogger(__name__)

BASE = "https://understat.com/getLeagueData"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EnchantmentBet/1.0)",
    "X-Requested-With": "XMLHttpRequest",
}

# api-sports league id -> understat league code. Understat covers only these.
LEAGUE_CODES = {
    39: "EPL",
    140: "La_liga",
    78: "Bundesliga",
    135: "Serie_A",
    61: "Ligue_1",
}

# Names too different for normalisation or token-subset matching to bridge.
# Keyed by normalised understat name -> normalised api-sports name.
ALIASES = {
    "wolverhampton wanderers": "wolves",
    "bayern munich": "bayern munchen",
    "borussia m gladbach": "borussia monchengladbach",
    "rasenballsport leipzig": "rb leipzig",
    "brest": "brestois",
}

# Club-name furniture that differs between providers and carries no identity.
_NOISE = {
    "fc", "cf", "ac", "sc", "afc", "ss", "as", "us", "rc", "sv", "vfl", "vfb",
    "tsg", "bsc", "ssc", "calcio", "club", "de", "futbol", "deportivo", "and",
    "real" ,"stade",
}

_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
CACHE_TTL = 24 * 3600


def normalise(name: str) -> str:
    """Comparable form of a club name: accent-free, lowercase, no punctuation,
    no bare numbers (founding years, '05') and no provider furniture."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t not in _NOISE and not t.isdigit()]
    return " ".join(tokens) or s.strip()


def match_team(understat_name: str, api_index: dict[str, str]) -> str | None:
    """Resolve an Understat club name to an api-sports team id.

    api_index maps normalised api-sports name -> team id. Tries exact
    normalised equality, then the alias table, then token-subset containment
    (which bridges "Newcastle United" vs "Newcastle").
    """
    key = normalise(understat_name)
    if key in api_index:
        return api_index[key]
    alias = ALIASES.get(key)
    if alias and alias in api_index:
        return api_index[alias]
    tokens = set(key.split())
    if tokens:
        subset = [
            tid for name, tid in api_index.items()
            if tokens <= set(name.split()) or set(name.split()) <= tokens
        ]
        if len(subset) == 1:
            return subset[0]
    return None


def _valid_history(entry: dict) -> bool:
    return all(
        isinstance(entry.get(k), (int, float)) for k in ("xG", "xGA", "scored", "missed")
    )


async def fetch_league_xg(api_league_id: int, season: int) -> dict[str, dict]:
    """Per-game xG for every team in a league season.

    Returns {normalised team name: {"xg_for_pg", "xg_against_pg", "matches"}}.
    Empty dict when the league is not covered or the fetch fails — callers
    then keep using actual goals.
    """
    code = LEAGUE_CODES.get(api_league_id)
    if not code:
        return {}
    cache_key = (code, int(season))
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    url = f"{BASE}/{code}/{season}"
    try:
        async with httpx.AsyncClient(timeout=40.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("understat fetch failed for %s %s: %s", code, season, exc)
        return {}

    teams = payload.get("teams")
    if not isinstance(teams, dict):
        logger.warning("understat returned an unexpected shape for %s %s", code, season)
        return {}

    out: dict[str, dict] = {}
    for team in teams.values():
        try:
            title = team["title"]
            history = [h for h in team["history"] if _valid_history(h)]
            if len(history) < 5:  # too few matches to be meaningful
                continue
            n = len(history)
            out[normalise(title)] = {
                "title": title,
                "xg_for_pg": round(sum(h["xG"] for h in history) / n, 3),
                "xg_against_pg": round(sum(h["xGA"] for h in history) / n, 3),
                "matches": n,
            }
        except Exception:
            continue

    if out:
        _CACHE[cache_key] = (time.time(), out)
        logger.info("understat: %s %s -> xG for %d teams", code, season, len(out))
    return out
