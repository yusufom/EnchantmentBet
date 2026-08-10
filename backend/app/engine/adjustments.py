"""Injury and news adjustments applied on top of the statistical models."""

from ..schemas import Factor, Injury, NewsItem

STATUS_WEIGHT = {"out": 1.0, "doubtful": 0.6, "questionable": 0.35}
MAX_INJURY_PENALTY = 0.18
MAX_NEWS_SWING = 0.03


def injury_multiplier(injuries: list[Injury], team_id: str) -> float:
    """Team strength multiplier in [1 - MAX_INJURY_PENALTY, 1]."""
    penalty = sum(
        inj.importance * STATUS_WEIGHT.get(inj.status, 0.35)
        for inj in injuries
        if inj.team_id == team_id
    )
    return 1.0 - min(penalty, MAX_INJURY_PENALTY)


def news_multiplier(news: list[NewsItem], team_id: str) -> float:
    """Small nudge from news sentiment, capped at +-MAX_NEWS_SWING."""
    items = [n for n in news if n.team_id == team_id]
    if not items:
        return 1.0
    avg = sum(n.sentiment for n in items) / len(items)
    return 1.0 + max(-MAX_NEWS_SWING, min(MAX_NEWS_SWING, avg * MAX_NEWS_SWING))


def build_factors(
    injuries: list[Injury],
    news: list[NewsItem],
    home_id: str,
    away_id: str,
    home_name: str,
    away_name: str,
    home_form: float,
    away_form: float,
) -> list[Factor]:
    factors: list[Factor] = []

    for team_id, team_name, other_side in (
        (home_id, home_name, "positive_away"),
        (away_id, away_name, "positive_home"),
    ):
        team_inj = [i for i in injuries if i.team_id == team_id]
        outs = [i for i in team_inj if i.status == "out"]
        doubts = [i for i in team_inj if i.status != "out"]
        if outs:
            factors.append(
                Factor(
                    label=f"{team_name} missing {len(outs)} player(s)",
                    detail=", ".join(f"{i.player} ({i.detail or i.status})" for i in outs[:4]),
                    impact=other_side,
                )
            )
        if doubts:
            factors.append(
                Factor(
                    label=f"{team_name}: {len(doubts)} doubtful",
                    detail=", ".join(i.player for i in doubts[:4]),
                    impact=other_side,
                )
            )

    if home_form - away_form > 0.35:
        factors.append(
            Factor(
                label=f"{home_name} in stronger form",
                detail=f"Form edge {home_form:+.2f} vs {away_form:+.2f}",
                impact="positive_home",
            )
        )
    elif away_form - home_form > 0.35:
        factors.append(
            Factor(
                label=f"{away_name} in stronger form",
                detail=f"Form edge {away_form:+.2f} vs {home_form:+.2f}",
                impact="positive_away",
            )
        )

    strong_news = sorted(news, key=lambda n: abs(n.sentiment), reverse=True)[:2]
    for item in strong_news:
        if abs(item.sentiment) < 0.3:
            continue
        team_is_home = item.team_id == home_id
        positive = item.sentiment > 0
        impact = (
            "positive_home" if team_is_home == positive else "positive_away"
        )
        factors.append(Factor(label="Team news", detail=item.headline, impact=impact))

    return factors
