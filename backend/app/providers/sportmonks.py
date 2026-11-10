"""SportMonks integration: pre-match odds and match facts.

The headline value here is **odds**. Bookmaker prices aggregate every public
signal plus the market's own money, and they are the strongest freely
available predictor of a football result — stronger than any of the
statistical models in this repo. They are used as a market prior blended into
the model's probabilities, not as a replacement, so the engine still has an
opinion of its own.

Match facts (venue, weather, referee, absentees, head-to-head, market view)
are collected for the prediction card and for Claude's prompt.

Plan limits observed on this key (free tier), verified by probing:
  available  fixtures, pre-match odds, statistics, lineups, events,
             sidelined, weather, venue, referees, standings, squads, h2h
  403        predictions/probabilities, value-bets, xGFixture, trends,
             news/pre-match, expected/fixtures, in-play odds
  leagues    Danish Superliga (271) and Scottish Premiership (501) only
"""

import asyncio
import logging
from datetime import date as date_cls
from statistics import median

import httpx

from ..config import get_settings
from ..schemas import MarketOdds, MatchFact
from .understat import normalise

logger = logging.getLogger(__name__)

BASE = "https://api.sportmonks.com/v3/football"

# api-sports league id -> sportmonks league id. Only what the plan covers.
LEAGUE_MAP = {179: 501, 119: 271}

FULL_TIME_RESULT = "full time result"
OVER_UNDER = "goals over/under"
BTTS = "both teams to score"

_fixture_cache: dict[str, list[dict]] = {}


def enabled() -> bool:
    return bool(get_settings().sportmonks_api_key)


def covered_league_names() -> list[str]:
    """Human-readable names of the leagues this plan can enrich."""
    from .apisports import FOOTBALL_LEAGUES

    return [FOOTBALL_LEAGUES.get(lid, str(lid)) for lid in LEAGUE_MAP]


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict:
    params["api_token"] = get_settings().sportmonks_api_key
    resp = await client.get(f"{BASE}{path}", params=params)
    if resp.status_code == 403:
        raise PermissionError(f"sportmonks plan does not allow {path}")
    resp.raise_for_status()
    return resp.json()


def _devig(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """Decimal odds -> true probabilities.

    Bookmakers price to sum above 100% (the overround/vig is their margin);
    dividing through by the total removes it.
    """
    implied = {label: 1.0 / odds for label, odds in pairs if odds and odds > 1.0}
    total = sum(implied.values())
    if not implied or total <= 0:
        return {}
    return {label: round(p / total, 4) for label, p in implied.items()}


def _consensus(rows: list[dict], market: str, labels: dict[str, str],
               total: str | None = None) -> dict[str, float]:
    """Median odds per outcome across bookmakers, then de-vigged."""
    buckets: dict[str, list[float]] = {}
    for row in rows:
        if (row.get("market_description") or "").lower() != market:
            continue
        if total is not None and str(row.get("total") or "") != total:
            continue
        key = labels.get((row.get("label") or "").strip().lower())
        if not key:
            continue
        try:
            odds = float(row["value"])
        except (TypeError, ValueError, KeyError):
            continue
        if odds > 1.0:
            buckets.setdefault(key, []).append(odds)
    if not buckets:
        return {}
    return _devig([(k, median(v)) for k, v in buckets.items()])


def parse_odds(rows: list[dict]) -> MarketOdds | None:
    """Build de-vigged market probabilities from raw odds rows."""
    if not rows:
        return None
    match_winner = _consensus(
        rows, FULL_TIME_RESULT,
        {"home": "home", "draw": "draw", "away": "away"},
    )
    if len(match_winner) != 3:
        return None
    ou = _consensus(rows, OVER_UNDER, {"over": "over", "under": "under"}, total="2.5")
    btts = _consensus(rows, BTTS, {"yes": "yes", "no": "no"})
    books = {r.get("bookmaker_id") for r in rows if r.get("bookmaker_id") is not None}
    return MarketOdds(
        match_winner=match_winner,
        over_under_25=ou or None,
        btts=btts or None,
        bookmakers=len(books),
    )


async def fixtures_for_date(client: httpx.AsyncClient, day: str) -> list[dict]:
    """All SportMonks fixtures on a date, with the includes match facts need."""
    if day in _fixture_cache:
        return _fixture_cache[day]
    try:
        payload = await _get(
            client, f"/fixtures/between/{day}/{day}",
            include="participants;league;venue;weatherReport;referees.referee;sidelined.player",
            per_page=50,
        )
    except Exception as exc:
        logger.warning("sportmonks fixtures failed for %s: %s", day, exc)
        return []
    data = [f for f in payload.get("data", []) if isinstance(f, dict)]
    _fixture_cache[day] = data
    return data


def _home_away(fixture: dict) -> tuple[dict | None, dict | None]:
    home = away = None
    for p in fixture.get("participants", []):
        loc = (p.get("meta") or {}).get("location")
        if loc == "home":
            home = p
        elif loc == "away":
            away = p
    return home, away


def _same_club(a: str, b: str) -> bool:
    """Tolerates suffix differences ("Hearts" vs "Heart of Midlothian")."""
    a, b = normalise(a), normalise(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def find_fixture(home: str, away: str, candidates: list[dict]) -> dict | None:
    """Resolve an api-sports fixture to its SportMonks twin.

    Orientation matters: participant order in the payload is arbitrary, so the
    home side is read from meta.location. A fixture with the teams reversed is
    the *other* leg, a different game — matching it would attach the home
    price to the away team and silently invert the prediction.
    """
    for fixture in candidates:
        sm_home, sm_away = _home_away(fixture)
        if not sm_home or not sm_away:
            continue
        if _same_club(home, sm_home.get("name", "")) and _same_club(away, sm_away.get("name", "")):
            return fixture
    return None


def build_facts(fixture: dict, odds: MarketOdds | None, h2h: dict | None) -> list[MatchFact]:
    """Human-readable pre-match facts for the card and for Claude."""
    facts: list[MatchFact] = []
    home, away = _home_away(fixture)

    if odds and odds.match_winner:
        fav = max(odds.match_winner, key=odds.match_winner.get)
        name = {"home": home, "away": away}.get(fav)
        who = (name or {}).get("name") if fav != "draw" else "A draw"
        facts.append(MatchFact(
            category="market",
            label="Bookmakers' favourite",
            value=f"{who} — {odds.match_winner[fav]*100:.0f}% implied"
                  + (f" (across {odds.bookmakers} books)" if odds.bookmakers > 1 else ""),
        ))

    venue = fixture.get("venue") or {}
    if venue.get("name"):
        cap = venue.get("capacity")
        facts.append(MatchFact(
            category="venue", label="Venue",
            value=venue["name"] + (f" · {cap:,} capacity" if cap else ""),
        ))

    weather = fixture.get("weatherreport") or fixture.get("weatherReport") or {}
    if isinstance(weather, dict) and weather:
        desc = weather.get("description")
        temp = (weather.get("temperature") or {}).get("day")
        wind = (weather.get("wind") or {}).get("speed")
        bits = [b for b in (desc, f"{temp}°C" if temp is not None else None,
                            f"wind {wind} m/s" if wind is not None else None) if b]
        if bits:
            facts.append(MatchFact(category="weather", label="Conditions",
                                   value=", ".join(str(b) for b in bits)))

    refs = fixture.get("referees") or []
    for ref in refs:
        person = ref.get("referee") or {}
        if person.get("name"):
            facts.append(MatchFact(category="referee", label="Referee",
                                   value=person["name"]))
            break

    sidelined = fixture.get("sidelined") or []
    by_team: dict[int, list[str]] = {}
    for entry in sidelined:
        player = (entry.get("player") or {}).get("name") or entry.get("player_name")
        team_id = entry.get("participant_id") or entry.get("team_id")
        if player and team_id:
            by_team.setdefault(team_id, []).append(player)
    for team in (home, away):
        if not team:
            continue
        out = by_team.get(team.get("id"), [])
        if out:
            facts.append(MatchFact(
                category="absence",
                label=f"{team.get('name')} absentees ({len(out)})",
                value=", ".join(out[:5]),
            ))

    if h2h:
        facts.append(MatchFact(
            category="h2h", label="Head-to-head",
            value=f"{h2h['home_wins']}W / {h2h['draws']}D / {h2h['away_wins']}L "
                  f"for {(home or {}).get('name', 'home')} in the last {h2h['played']}",
        ))
    return facts


async def h2h_record(client: httpx.AsyncClient, home_id: int, away_id: int) -> dict | None:
    try:
        payload = await _get(client, f"/fixtures/head-to-head/{home_id}/{away_id}",
                             include="scores", per_page=20)
    except Exception:
        return None
    hw = aw = dr = 0
    for fx in (payload.get("data") or [])[:10]:
        scores = [s for s in (fx.get("scores") or []) if s.get("description") == "CURRENT"]
        goals = {s.get("score", {}).get("participant"): s.get("score", {}).get("goals")
                 for s in scores}
        h, a = goals.get("home"), goals.get("away")
        if h is None or a is None:
            continue
        if h > a: hw += 1
        elif a > h: aw += 1
        else: dr += 1
    played = hw + aw + dr
    return {"home_wins": hw, "away_wins": aw, "draws": dr, "played": played} if played else None


async def enrich(api_league_id: int, day: str, home: str, away: str) -> tuple[MarketOdds | None, list[MatchFact]]:
    """Odds + match facts for one fixture. ({}, []) when unavailable."""
    if not enabled() or api_league_id not in LEAGUE_MAP:
        return None, []
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            candidates = await fixtures_for_date(client, day)
            fixture = find_fixture(home, away, candidates)
            if not fixture:
                return None, []
            rows = []
            try:
                payload = await _get(client, f"/odds/pre-match/fixtures/{fixture['id']}")
                rows = payload.get("data") or []
            except Exception as exc:
                logger.info("sportmonks odds unavailable for %s: %s", fixture["id"], exc)
            odds = parse_odds(rows)
            h, a = _home_away(fixture)
            h2h = await h2h_record(client, h["id"], a["id"]) if h and a else None
            return odds, build_facts(fixture, odds, h2h)
    except Exception:
        logger.warning("sportmonks enrichment failed for %s v %s", home, away)
        return None, []
