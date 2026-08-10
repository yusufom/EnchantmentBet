"""Elo-style rating utilities.

Ratings are centered on 1500. When a provider cannot supply a maintained Elo,
we derive a season-performance rating from win rate and scoring margin so the
rest of the engine can treat every sport uniformly.
"""


def win_probability(rating_a: float, rating_b: float, advantage_a: float = 0.0) -> float:
    """Two-outcome Elo expectation for A beating B."""
    return 1.0 / (1.0 + 10 ** (-((rating_a + advantage_a) - rating_b) / 400.0))


def rating_from_performance(
    win_pct: float, margin_per_game: float, margin_scale: float, matches: int
) -> float:
    """Derive an Elo-like rating from season performance.

    margin_scale converts one unit of average scoring margin into rating
    points (football goals move ratings much more than basketball points).
    Shrinks toward 1500 when the sample is small.
    """
    raw = 1500.0 + (win_pct - 0.5) * 500.0 + margin_per_game * margin_scale
    weight = min(matches, 20) / 20.0
    return 1500.0 + (raw - 1500.0) * weight


def form_score(form: list[str], window: int = 5) -> float:
    """Recent form in [-1, 1]; most recent result weighs most."""
    recent = form[:window]
    if not recent:
        return 0.0
    total = 0.0
    weight_sum = 0.0
    for i, result in enumerate(recent):
        w = 1.0 - i * 0.15
        value = {"W": 1.0, "D": 0.0, "L": -1.0}.get(result, 0.0)
        total += value * w
        weight_sum += w
    return total / weight_sum
