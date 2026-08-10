"""Tennis model: point -> game -> set -> match Markov chain.

From each player's serve-point win probability we compute game hold
probabilities analytically, then walk a memoized recursion through set and
tiebreak states. Match probability assumes set outcomes are i.i.d., which is
a standard and well-behaved approximation.
"""

from functools import lru_cache

AVG_SERVE_PTS_WON = 0.62
AVG_RETURN_PTS_WON = 1.0 - AVG_SERVE_PTS_WON


def point_probs(
    a_serve_won: float, a_return_won: float, b_serve_won: float, b_return_won: float
) -> tuple[float, float]:
    """(P(A wins point on A serve), P(A wins point on B serve))."""
    pa_serve = a_serve_won + (AVG_RETURN_PTS_WON - b_return_won)
    pa_return = a_return_won + (AVG_SERVE_PTS_WON - b_serve_won)
    clamp = lambda x: max(0.35, min(0.88, x))
    return clamp(pa_serve), clamp(pa_return)


def game_win_prob(p: float) -> float:
    """P(server wins the game) given point win prob p."""
    q = 1.0 - p
    deuce = p * p / (1.0 - 2.0 * p * q)
    return p**4 * (1.0 + 4.0 * q + 10.0 * q * q) + 20.0 * p**3 * q**3 * deuce


def _tiebreak_server(point_index: int) -> int:
    """0 if the tiebreak's first server serves this 0-indexed point."""
    return 0 if ((point_index + 1) // 2) % 2 == 0 else 1


def tiebreak_win_prob(pa_serve: float, pa_return: float) -> float:
    """P(A wins a 7-point tiebreak), A serving first."""

    @lru_cache(maxsize=None)
    def rec(a: int, b: int) -> float:
        if a >= 7 and a - b >= 2:
            return 1.0
        if b >= 7 and b - a >= 2:
            return 0.0
        if a == 6 and b == 6:
            # From 6-6 points come in serve-balanced pairs; solve the
            # deuce-like parity state directly.
            win_pair = pa_serve * pa_return
            lose_pair = (1.0 - pa_serve) * (1.0 - pa_return)
            return win_pair / (win_pair + lose_pair)
        p = pa_serve if _tiebreak_server(a + b) == 0 else pa_return
        return p * rec(a + 1, b) + (1.0 - p) * rec(a, b + 1)

    result = rec(0, 0)
    rec.cache_clear()
    return result


def set_win_prob(pa_serve: float, pa_return: float, a_serves_first: bool = True) -> float:
    """P(A wins the set)."""
    hold_a = game_win_prob(pa_serve)
    break_a = 1.0 - game_win_prob(1.0 - pa_return)  # P(A wins B's service game)
    tb = tiebreak_win_prob(pa_serve, pa_return)

    @lru_cache(maxsize=None)
    def rec(ga: int, gb: int, a_serving: bool) -> float:
        if ga == 7 or (ga == 6 and gb <= 4):
            return 1.0
        if gb == 7 or (gb == 6 and ga <= 4):
            return 0.0
        if ga == 6 and gb == 6:
            return tb
        p = hold_a if a_serving else break_a
        return p * rec(ga + 1, gb, not a_serving) + (1.0 - p) * rec(ga, gb + 1, not a_serving)

    result = rec(0, 0, a_serves_first)
    rec.cache_clear()
    return result


def match_win_prob(set_prob: float, best_of: int = 3) -> float:
    s, t = set_prob, 1.0 - set_prob
    if best_of == 5:
        return s**3 * (1.0 + 3.0 * t + 6.0 * t * t)
    return s * s * (1.0 + 2.0 * t)


def set_score_distribution(set_prob: float, best_of: int = 3) -> dict[str, float]:
    """Probability of each final set score (best of 3)."""
    s, t = set_prob, 1.0 - set_prob
    if best_of == 5:
        return {
            "3-0": s**3,
            "3-1": 3.0 * s**3 * t,
            "3-2": 6.0 * s**3 * t * t,
            "2-3": 6.0 * t**3 * s * s,
            "1-3": 3.0 * t**3 * s,
            "0-3": t**3,
        }
    return {
        "2-0": s * s,
        "2-1": 2.0 * s * s * t,
        "1-2": 2.0 * t * t * s,
        "0-2": t * t,
    }
