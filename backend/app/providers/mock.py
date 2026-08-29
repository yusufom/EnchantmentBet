"""Deterministic mock provider.

Generates realistic fixtures, stats, injuries and news without any API key so
the whole app runs out of the box. Team quality is stable across dates
(seeded by team name); the day's schedule is seeded by (sport, date), so
refreshing a date reproduces that date's slate.
"""

import random
from datetime import datetime, timedelta, timezone

from ..schemas import (
    Competitor,
    Fixture,
    FixtureContext,
    Injury,
    NewsItem,
    Sport,
    TeamStats,
)
from .base import SportProvider

FOOTBALL_TEAMS = {
    # name: quality 0..1
    "Manchester City": 0.93, "Arsenal": 0.90, "Liverpool": 0.91, "Chelsea": 0.78,
    "Tottenham": 0.72, "Manchester United": 0.70, "Newcastle": 0.74, "Aston Villa": 0.73,
    "Brighton": 0.66, "West Ham": 0.58, "Crystal Palace": 0.60, "Fulham": 0.57,
    "Brentford": 0.55, "Everton": 0.52, "Wolves": 0.50, "Nottingham Forest": 0.56,
    "Bournemouth": 0.54, "Leicester": 0.45, "Ipswich": 0.40, "Southampton": 0.38,
}
FOOTBALL_LEAGUE = ("Premier League", "England")

BASKETBALL_TEAMS = {
    "Boston Celtics": 0.92, "Oklahoma City Thunder": 0.91, "Denver Nuggets": 0.85,
    "Minnesota Timberwolves": 0.80, "New York Knicks": 0.82, "Milwaukee Bucks": 0.76,
    "Cleveland Cavaliers": 0.84, "Dallas Mavericks": 0.78, "Phoenix Suns": 0.68,
    "LA Clippers": 0.70, "Los Angeles Lakers": 0.74, "Golden State Warriors": 0.72,
    "Miami Heat": 0.64, "Philadelphia 76ers": 0.66, "Indiana Pacers": 0.75,
    "Sacramento Kings": 0.62, "Orlando Magic": 0.69, "Houston Rockets": 0.71,
    "Memphis Grizzlies": 0.73, "New Orleans Pelicans": 0.60, "Atlanta Hawks": 0.55,
    "Chicago Bulls": 0.50, "Toronto Raptors": 0.45, "San Antonio Spurs": 0.58,
    "Detroit Pistons": 0.52, "Utah Jazz": 0.40, "Brooklyn Nets": 0.42,
    "Charlotte Hornets": 0.38, "Portland Trail Blazers": 0.44, "Washington Wizards": 0.35,
}
BASKETBALL_LEAGUE = ("NBA", "USA")

TENNIS_PLAYERS = {
    "Carlos Alcaraz": 0.94, "Jannik Sinner": 0.95, "Novak Djokovic": 0.88,
    "Alexander Zverev": 0.84, "Daniil Medvedev": 0.82, "Taylor Fritz": 0.79,
    "Casper Ruud": 0.76, "Andrey Rublev": 0.75, "Alex de Minaur": 0.77,
    "Grigor Dimitrov": 0.72, "Stefanos Tsitsipas": 0.74, "Tommy Paul": 0.73,
    "Holger Rune": 0.71, "Hubert Hurkacz": 0.70, "Ben Shelton": 0.69,
    "Frances Tiafoe": 0.66, "Sebastian Korda": 0.64, "Karen Khachanov": 0.65,
    "Ugo Humbert": 0.63, "Lorenzo Musetti": 0.68, "Felix Auger-Aliassime": 0.62,
    "Jack Draper": 0.72, "Arthur Fils": 0.64, "Alejandro Tabilo": 0.58,
}
TENNIS_EVENTS = [
    ("ATP Masters 1000", "Hard"), ("ATP 500", "Hard"), ("ATP 250", "Clay"),
    ("ATP 500", "Grass"), ("ATP Masters 1000", "Clay"),
]

FIRST_NAMES = ["James", "Marcus", "Diego", "Luka", "Pedro", "Kai", "Mateo", "Andre",
               "Youssef", "Tomas", "Rafael", "Emile", "Victor", "Sergio", "Nathan"]
LAST_NAMES = ["Silva", "Johnson", "Martinez", "Kovac", "Peters", "Moreau", "Costa",
              "Williams", "Baker", "Rossi", "Fernandez", "Schmidt", "Dubois", "Okafor"]

INJURY_DETAILS = ["hamstring", "knee", "ankle", "calf", "groin", "back", "illness", "shoulder"]

NEWS_TEMPLATES_POS = [
    "{team} boosted as key player returns to full training",
    "{team} confirm squad at full strength ahead of clash",
    "Morale high at {team} after strong week of preparation",
]
NEWS_TEMPLATES_NEG = [
    "{team} sweat on fitness of key starter before matchup",
    "Turbulent week at {team} amid reports of dressing-room tension",
    "{team} face selection headache with several players carrying knocks",
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def _team_rng(sport: str, name: str) -> random.Random:
    return random.Random(f"{sport}:{name}")


class MockProvider(SportProvider):
    data_source = "mock"

    def __init__(self, sport: Sport):
        self.sport = sport

    async def get_fixture_contexts(self, date: str) -> list[FixtureContext]:
        rng = random.Random(f"{self.sport}:{date}")
        if self.sport == "football":
            return self._football(date, rng)
        if self.sport == "basketball":
            return self._basketball(date, rng)
        return self._tennis(date, rng)

    async def get_results(self, date: str) -> dict[str, dict]:
        """Deterministic plausible final scores for the date's mock slate."""
        if self.sport == "tennis":
            return {}
        results = {}
        for ctx in await self.get_fixture_contexts(date):
            rng = random.Random(f"result:{ctx.fixture.id}")
            edge = (ctx.home_stats.rating - ctx.away_stats.rating) / 400.0
            if self.sport == "football":
                home = min(5, max(0, int(rng.gauss(1.5 + edge, 1.1) + 0.5)))
                away = min(5, max(0, int(rng.gauss(1.2 - edge, 1.1) + 0.5)))
            else:  # basketball
                home = max(70, int(rng.gauss(112 + edge * 6, 9) + 0.5))
                away = max(70, int(rng.gauss(109 - edge * 6, 9) + 0.5))
                if home == away:
                    home += 1
            ht_home = sum(1 for _ in range(home) if rng.random() < 0.45)
            ht_away = sum(1 for _ in range(away) if rng.random() < 0.45)
            results[ctx.fixture.id] = {
                "home": home, "away": away, "status": "FT",
                "ht_home": ht_home, "ht_away": ht_away,
            }
        return results

    # -- schedule helpers -------------------------------------------------

    def _pairings(self, pool: dict[str, float], count: int, rng: random.Random):
        names = list(pool)
        rng.shuffle(names)
        return [(names[2 * i], names[2 * i + 1]) for i in range(min(count, len(names) // 2))]

    def _kickoff(self, date: str, rng: random.Random, hours: tuple[int, int]) -> datetime:
        base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return base + timedelta(hours=rng.randint(*hours), minutes=rng.choice([0, 15, 30, 45]))

    def _form(self, quality: float, rng: random.Random, draws: bool) -> list[str]:
        form = []
        for _ in range(5):
            roll = rng.random()
            if draws and abs(roll - 0.5) < 0.12:
                form.append("D")
            elif roll < 0.25 + quality * 0.55:
                form.append("W")
            else:
                form.append("L")
        return form

    def _injuries(self, team_id: str, rng: random.Random) -> list[Injury]:
        injuries = []
        for _ in range(rng.choices([0, 1, 2, 3], weights=[45, 30, 17, 8])[0]):
            injuries.append(
                Injury(
                    player=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                    team_id=team_id,
                    status=rng.choices(["out", "doubtful", "questionable"], weights=[45, 35, 20])[0],
                    detail=rng.choice(INJURY_DETAILS),
                    importance=round(rng.uniform(0.015, 0.07), 3),
                )
            )
        return injuries

    def _news(self, team_id: str, team_name: str, date: str, rng: random.Random) -> list[NewsItem]:
        items = []
        if rng.random() < 0.55:
            positive = rng.random() < 0.5
            template = rng.choice(NEWS_TEMPLATES_POS if positive else NEWS_TEMPLATES_NEG)
            items.append(
                NewsItem(
                    team_id=team_id,
                    headline=template.format(team=team_name),
                    source="Mock Sports Wire",
                    published_at=datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    - timedelta(hours=rng.randint(4, 30)),
                    sentiment=round(rng.uniform(0.3, 0.9) * (1 if positive else -1), 2),
                )
            )
        return items

    # -- sports -----------------------------------------------------------

    def _football(self, date: str, rng: random.Random) -> list[FixtureContext]:
        contexts = []
        for idx, (home, away) in enumerate(self._pairings(FOOTBALL_TEAMS, 8, rng)):
            hq, aq = FOOTBALL_TEAMS[home], FOOTBALL_TEAMS[away]
            fixture = Fixture(
                id=f"mock-fb-{date}-{idx}",
                sport="football",
                league=FOOTBALL_LEAGUE[0],
                country=FOOTBALL_LEAGUE[1],
                start_time=self._kickoff(date, rng, (12, 20)),
                home=Competitor(id=_slug(home), name=home),
                away=Competitor(id=_slug(away), name=away),
                venue=f"{home} Stadium",
            )
            contexts.append(
                FixtureContext(
                    fixture=fixture,
                    home_stats=self._football_stats(home, hq),
                    away_stats=self._football_stats(away, aq),
                    injuries=self._injuries(_slug(home), rng) + self._injuries(_slug(away), rng),
                    news=self._news(_slug(home), home, date, rng)
                    + self._news(_slug(away), away, date, rng),
                    h2h_home_wins=rng.randint(0, 5),
                    h2h_away_wins=rng.randint(0, 5),
                    h2h_draws=rng.randint(0, 3),
                    data_quality=0.6,
                )
            )
        return contexts

    def _football_stats(self, name: str, quality: float) -> TeamStats:
        rng = _team_rng("football", name)
        scored = 0.9 + quality * 1.5 + rng.uniform(-0.1, 0.1)
        conceded = 2.1 - quality * 1.3 + rng.uniform(-0.1, 0.1)
        return TeamStats(
            competitor_id=_slug(name),
            rating=1500.0 + (quality - 0.5) * 400.0,
            matches_played=20,
            form=self._form(quality, rng, draws=True),
            goals_scored_pg=round(scored, 2),
            goals_conceded_pg=round(max(conceded, 0.5), 2),
        )

    def _basketball(self, date: str, rng: random.Random) -> list[FixtureContext]:
        contexts = []
        for idx, (home, away) in enumerate(self._pairings(BASKETBALL_TEAMS, 7, rng)):
            hq, aq = BASKETBALL_TEAMS[home], BASKETBALL_TEAMS[away]
            fixture = Fixture(
                id=f"mock-bb-{date}-{idx}",
                sport="basketball",
                league=BASKETBALL_LEAGUE[0],
                country=BASKETBALL_LEAGUE[1],
                start_time=self._kickoff(date, rng, (17, 23)),
                home=Competitor(id=_slug(home), name=home),
                away=Competitor(id=_slug(away), name=away),
            )
            contexts.append(
                FixtureContext(
                    fixture=fixture,
                    home_stats=self._basketball_stats(home, hq),
                    away_stats=self._basketball_stats(away, aq),
                    injuries=self._injuries(_slug(home), rng) + self._injuries(_slug(away), rng),
                    news=self._news(_slug(home), home, date, rng)
                    + self._news(_slug(away), away, date, rng),
                    h2h_home_wins=rng.randint(0, 4),
                    h2h_away_wins=rng.randint(0, 4),
                    data_quality=0.6,
                )
            )
        return contexts

    def _basketball_stats(self, name: str, quality: float) -> TeamStats:
        rng = _team_rng("basketball", name)
        return TeamStats(
            competitor_id=_slug(name),
            rating=1500.0 + (quality - 0.5) * 450.0,
            matches_played=40,
            form=self._form(quality, rng, draws=False),
            off_rating=round(104.0 + quality * 14.0 + rng.uniform(-1, 1), 1),
            def_rating=round(120.0 - quality * 14.0 + rng.uniform(-1, 1), 1),
            pace=round(96.0 + rng.uniform(0, 6), 1),
        )

    def _tennis(self, date: str, rng: random.Random) -> list[FixtureContext]:
        contexts = []
        event, surface = rng.choice(TENNIS_EVENTS)
        for idx, (a, b) in enumerate(self._pairings(TENNIS_PLAYERS, 8, rng)):
            qa, qb = TENNIS_PLAYERS[a], TENNIS_PLAYERS[b]
            fixture = Fixture(
                id=f"mock-tn-{date}-{idx}",
                sport="tennis",
                league=event,
                start_time=self._kickoff(date, rng, (9, 19)),
                home=Competitor(id=_slug(a), name=a),
                away=Competitor(id=_slug(b), name=b),
                surface=surface,
                best_of=3,
            )
            contexts.append(
                FixtureContext(
                    fixture=fixture,
                    home_stats=self._tennis_stats(a, qa, surface),
                    away_stats=self._tennis_stats(b, qb, surface),
                    injuries=self._injuries(_slug(a), rng)[:1] + self._injuries(_slug(b), rng)[:1],
                    news=self._news(_slug(a), a, date, rng) + self._news(_slug(b), b, date, rng),
                    h2h_home_wins=rng.randint(0, 4),
                    h2h_away_wins=rng.randint(0, 4),
                    data_quality=0.6,
                )
            )
        return contexts

    def _tennis_stats(self, name: str, quality: float, surface: str) -> TeamStats:
        rng = _team_rng("tennis", name)
        surface_adj = rng.uniform(-0.006, 0.006)  # stable per player, proxies surface skill
        return TeamStats(
            competitor_id=_slug(name),
            rating=1500.0 + (quality - 0.5) * 500.0,
            matches_played=30,
            form=self._form(quality, rng, draws=False),
            serve_pts_won=round(0.55 + quality * 0.115 + surface_adj, 3),
            return_pts_won=round(0.31 + quality * 0.115 + surface_adj, 3),
        )
