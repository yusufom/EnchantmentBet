"""Dixon-Coles adjusted Poisson model for football.

Builds a full scoreline probability matrix from expected goals, applies the
Dixon-Coles low-score correlation correction, and derives 1X2, over/under
and both-teams-to-score probabilities from it.
"""

import math

MAX_GOALS = 10
RHO = -0.10  # Dixon-Coles low-score correlation
LEAGUE_AVG_HOME_GOALS = 1.50
LEAGUE_AVG_AWAY_GOALS = 1.20
LEAGUE_AVG_GOALS = (LEAGUE_AVG_HOME_GOALS + LEAGUE_AVG_AWAY_GOALS) / 2


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def _tau(i: int, j: int, lam_h: float, lam_a: float) -> float:
    if i == 0 and j == 0:
        return 1.0 - lam_h * lam_a * RHO
    if i == 0 and j == 1:
        return 1.0 + lam_h * RHO
    if i == 1 and j == 0:
        return 1.0 + lam_a * RHO
    if i == 1 and j == 1:
        return 1.0 - RHO
    return 1.0


def expected_goals(
    home_scored_pg: float,
    home_conceded_pg: float,
    away_scored_pg: float,
    away_conceded_pg: float,
    home_strength_mult: float = 1.0,
    away_strength_mult: float = 1.0,
) -> tuple[float, float]:
    """Expected goals for each side from attack/defence rates.

    Attack and defence are expressed relative to the league average, then
    recombined with the home/away scoring baselines (multiplicative model).
    """
    home_attack = max(home_scored_pg, 0.1) / LEAGUE_AVG_GOALS
    home_defence = max(home_conceded_pg, 0.1) / LEAGUE_AVG_GOALS
    away_attack = max(away_scored_pg, 0.1) / LEAGUE_AVG_GOALS
    away_defence = max(away_conceded_pg, 0.1) / LEAGUE_AVG_GOALS

    lam_home = LEAGUE_AVG_HOME_GOALS * home_attack * away_defence * home_strength_mult
    lam_away = LEAGUE_AVG_AWAY_GOALS * away_attack * home_defence * away_strength_mult
    return max(0.15, min(lam_home, 5.0)), max(0.15, min(lam_away, 5.0))


def score_matrix(lam_home: float, lam_away: float) -> list[list[float]]:
    matrix = [
        [
            _poisson_pmf(i, lam_home)
            * _poisson_pmf(j, lam_away)
            * _tau(i, j, lam_home, lam_away)
            for j in range(MAX_GOALS + 1)
        ]
        for i in range(MAX_GOALS + 1)
    ]
    total = sum(sum(row) for row in matrix)
    return [[p / total for p in row] for row in matrix]


def derive_markets(matrix: list[list[float]]) -> dict:
    home = draw = away = over25 = btts = 0.0
    best_score, best_p = (0, 0), -1.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
            if i + j >= 3:
                over25 += p
            if i >= 1 and j >= 1:
                btts += p
            if p > best_p:
                best_p, best_score = p, (i, j)
    return {
        "home": home,
        "draw": draw,
        "away": away,
        "over_2.5": over25,
        "under_2.5": 1.0 - over25,
        "btts_yes": btts,
        "btts_no": 1.0 - btts,
        "most_likely_score": best_score,
    }
