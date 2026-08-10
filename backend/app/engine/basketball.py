"""Basketball model: pace-adjusted offensive/defensive efficiency.

Expected score for each side comes from its offensive rating scaled by the
opponent's defensive rating and the blended game pace. The point margin is
treated as normally distributed to get a win probability, spread and total.
"""

import math

LEAGUE_AVG_RATING = 112.0  # points per 100 possessions
LEAGUE_AVG_PACE = 99.0  # possessions per game
HOME_COURT_POINTS = 2.6
MARGIN_SIGMA = 11.5  # stdev of NBA game margins


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def expected_points(
    home_off: float,
    home_def: float,
    away_off: float,
    away_def: float,
    home_pace: float,
    away_pace: float,
    home_strength_mult: float = 1.0,
    away_strength_mult: float = 1.0,
) -> tuple[float, float]:
    pace = (home_pace + away_pace) / 2.0
    # Efficiency vs this opponent: own offense scaled by how the opponent's
    # defense compares to league average.
    home_eff = home_off * (away_def / LEAGUE_AVG_RATING) * home_strength_mult
    away_eff = away_off * (home_def / LEAGUE_AVG_RATING) * away_strength_mult
    home_pts = pace * home_eff / 100.0 + HOME_COURT_POINTS / 2.0
    away_pts = pace * away_eff / 100.0 - HOME_COURT_POINTS / 2.0
    return home_pts, away_pts


def derive_markets(home_pts: float, away_pts: float) -> dict:
    margin = home_pts - away_pts
    p_home = normal_cdf(margin / MARGIN_SIGMA)
    total = home_pts + away_pts
    total_line = round(total * 2) / 2.0
    # Probability the total goes over its own expected line is ~0.5 by
    # construction; expose the line plus over prob vs the nearest whole line.
    return {
        "home": p_home,
        "away": 1.0 - p_home,
        "spread": round(margin, 1),
        "total_line": total_line,
        "expected_home": home_pts,
        "expected_away": away_pts,
    }
