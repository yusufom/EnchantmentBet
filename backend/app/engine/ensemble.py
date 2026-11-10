"""Ensemble layer: combines the sport model, Elo expectation, recent form,
head-to-head record, injuries and news into final market probabilities.
"""

from datetime import datetime, timezone

from ..config import get_settings
from ..schemas import Factor, FixtureContext, Market, MatchFact, Prediction, TeamStats
from . import basketball, elo, poisson, tennis
from .adjustments import build_factors, injury_multiplier, news_multiplier

# Weight of the statistical model vs the Elo expectation per sport.
MODEL_WEIGHT = {"football": 0.65, "basketball": 0.60, "tennis": 0.60}
HOME_ADVANTAGE_ELO = {"football": 65.0, "basketball": 80.0, "tennis": 0.0}
FORM_SWING = 0.04  # max probability shift from recent form
H2H_SWING = 0.02  # max probability shift from head-to-head record


def _clamp01(x: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, x))


def _context_edges(ctx: FixtureContext) -> tuple[float, float, float]:
    """(home_form, away_form, home_edge) where home_edge shifts the home
    win-probability share by at most FORM_SWING + H2H_SWING."""
    home_form = elo.form_score(ctx.home_stats.form)
    away_form = elo.form_score(ctx.away_stats.form)
    edge = (home_form - away_form) / 2.0 * FORM_SWING

    h2h_total = ctx.h2h_home_wins + ctx.h2h_away_wins + ctx.h2h_draws
    if h2h_total >= 4:
        edge += (ctx.h2h_home_wins - ctx.h2h_away_wins) / h2h_total * H2H_SWING
    return home_form, away_form, edge


def _confidence(top: float, second: float, data_quality: float) -> tuple[float, str]:
    margin = top - second
    conf = _clamp01((0.40 + margin * 1.1) * (0.75 + 0.25 * data_quality), 0.20, 0.95)
    label = "high" if conf >= 0.72 else "medium" if conf >= 0.52 else "low"
    return round(conf, 3), label


def _pick(outcomes: dict[str, float]) -> tuple[str, float]:
    pick = max(outcomes, key=outcomes.get)
    return pick, round(outcomes[pick], 4)


def _market(name: str, outcomes: dict[str, float]) -> Market:
    rounded = {k: round(v, 4) for k, v in outcomes.items()}
    pick, prob = _pick(rounded)
    return Market(name=name, outcomes=rounded, pick=pick, pick_probability=prob)


def predict_fixture(ctx: FixtureContext) -> Prediction:
    sport = ctx.fixture.sport
    home_mult = injury_multiplier(ctx.injuries, ctx.home_stats.competitor_id) * news_multiplier(
        ctx.news, ctx.home_stats.competitor_id
    )
    away_mult = injury_multiplier(ctx.injuries, ctx.away_stats.competitor_id) * news_multiplier(
        ctx.news, ctx.away_stats.competitor_id
    )
    home_form, away_form, home_edge = _context_edges(ctx)

    # Injuries also depress the Elo expectation (~120 rating pts at max penalty).
    elo_home = ctx.home_stats.rating - (1.0 - home_mult) * 650.0
    elo_away = ctx.away_stats.rating - (1.0 - away_mult) * 650.0
    elo_p_home = elo.win_probability(elo_home, elo_away, HOME_ADVANTAGE_ELO[sport])
    w = MODEL_WEIGHT[sport]

    if sport == "football":
        prediction = _predict_football(ctx, home_mult, away_mult, elo_p_home, w, home_edge)
    elif sport == "basketball":
        prediction = _predict_basketball(ctx, home_mult, away_mult, elo_p_home, w, home_edge)
    else:
        prediction = _predict_tennis(ctx, home_mult, away_mult, elo_p_home, w, home_edge)

    markets, predicted_score, exp_home, exp_away, algorithm = prediction
    if ctx.odds:
        markets, algorithm = _apply_market(markets, ctx, algorithm)
    main = markets[0]
    sorted_probs = sorted(main.outcomes.values(), reverse=True)
    conf, conf_label = _confidence(sorted_probs[0], sorted_probs[1], ctx.data_quality)

    factors: list[Factor] = build_factors(
        ctx.injuries,
        ctx.news,
        ctx.home_stats.competitor_id,
        ctx.away_stats.competitor_id,
        ctx.fixture.home.name,
        ctx.fixture.away.name,
        home_form,
        away_form,
    )
    for stats, comp, side in (
        (ctx.home_stats, ctx.fixture.home, "home"),
        (ctx.away_stats, ctx.fixture.away, "away"),
    ):
        if stats.xg_for_pg is None or stats.goals_scored_pg is None:
            continue
        # Scoring far above or below the chances created rarely persists, so
        # the table can flatter or hide a team. Worth saying out loud.
        gap = stats.goals_scored_pg - stats.xg_for_pg
        if abs(gap) >= 0.25:
            over = gap > 0
            factors.append(
                Factor(
                    label=f"{comp.name} {'over' if over else 'under'}performing their xG",
                    detail=(
                        f"Scoring {stats.goals_scored_pg:.2f}/game from "
                        f"{stats.xg_for_pg:.2f} xG — {'finishing has flattered them'
                        if over else 'chances have not been converted'}"
                    ),
                    impact=("positive_away" if over else "positive_home")
                    if side == "home"
                    else ("positive_home" if over else "positive_away"),
                )
            )

    if abs(ctx.home_stats.rating - ctx.away_stats.rating) > 80:
        stronger = ctx.fixture.home if ctx.home_stats.rating > ctx.away_stats.rating else ctx.fixture.away
        factors.insert(
            0,
            Factor(
                label=f"{stronger.name} rated clearly stronger",
                detail=f"Rating {ctx.home_stats.rating:.0f} vs {ctx.away_stats.rating:.0f}",
                impact="positive_home" if stronger is ctx.fixture.home else "positive_away",
            ),
        )

    facts = list(ctx.match_facts)
    disagreement = market_disagreement(
        main.outcomes, ctx.odds, ctx.fixture.home.name, ctx.fixture.away.name
    )
    if disagreement:
        facts.append(disagreement)

    return Prediction(
        sport=sport,
        date=ctx.fixture.start_time.strftime("%Y-%m-%d") if ctx.fixture.start_time else "",
        fixture_id=ctx.fixture.id,
        fixture=ctx.fixture,
        markets=markets,
        predicted_score=predicted_score,
        expected_home=round(exp_home, 2) if exp_home is not None else None,
        expected_away=round(exp_away, 2) if exp_away is not None else None,
        confidence=conf,
        confidence_label=conf_label,
        factors=factors,
        injuries=ctx.injuries,
        news=ctx.news,
        match_facts=facts,
        odds=ctx.odds,
        algorithm=algorithm,
        data_source=ctx.source,
        data_quality=round(ctx.data_quality, 3),
        generated_at=datetime.now(timezone.utc),
    )


def _apply_market(markets, ctx, algorithm):
    """Blend de-vigged bookmaker probabilities into the model's markets.

    Odds aggregate every public signal plus real money, so they are a strong
    prior — but blending all the way to the market would just reproduce the
    bookmaker's book, edge and all. The weight keeps the model's own view in
    the mix.
    """
    w = max(0.0, min(1.0, get_settings().odds_weight))
    if w <= 0:
        return markets, algorithm
    odds = ctx.odds
    by_name = {m.name: m for m in markets}
    pairs = [("match_winner", odds.match_winner),
             ("over_under_2.5", odds.over_under_25),
             ("btts", odds.btts)]
    touched = False
    for name, market_probs in pairs:
        target = by_name.get(name)
        if not target or not market_probs:
            continue
        if set(market_probs) != set(target.outcomes):
            continue
        blended = {
            k: (1.0 - w) * target.outcomes[k] + w * market_probs[k]
            for k in target.outcomes
        }
        total = sum(blended.values()) or 1.0
        target.outcomes = {k: round(v / total, 4) for k, v in blended.items()}
        target.pick = max(target.outcomes, key=target.outcomes.get)
        target.pick_probability = round(target.outcomes[target.pick], 4)
        touched = True
    return markets, (algorithm + " + market odds" if touched else algorithm)


def market_disagreement(model_probs: dict, odds, home: str, away: str) -> MatchFact | None:
    """Flag where the model and the market see the game differently.

    A gap is either an edge or a sign the model is missing something — either
    way it is the most interesting thing on the card.
    """
    if not odds or not odds.match_winner:
        return None
    labels = {"home": home, "draw": "a draw", "away": away}
    gaps = {
        k: model_probs.get(k, 0.0) - odds.match_winner.get(k, 0.0)
        for k in odds.match_winner
    }
    outcome = max(gaps, key=gaps.get)
    gap = gaps[outcome]
    if gap < 0.08:
        return None
    return MatchFact(
        category="market",
        label="Model disagrees with the market",
        value=(f"Model rates {labels[outcome]} at "
               f"{model_probs.get(outcome, 0)*100:.0f}% vs the market's "
               f"{odds.match_winner[outcome]*100:.0f}%"),
    )


def _blend_two_way(model_p: float, elo_p: float, w: float, home_edge: float) -> float:
    return _clamp01(w * model_p + (1.0 - w) * elo_p + home_edge)


def scoring_rates(stats: TeamStats) -> tuple[float, float]:
    """Effective (scored, conceded) per game, blending expected goals with
    actual ones where xG is available.

    Actual scorelines carry finishing luck that does not repeat; xG measures
    the chances created and conceded, which does. The blend keeps some actual
    signal because xG models have their own error.
    """
    scored = stats.goals_scored_pg if stats.goals_scored_pg is not None else 1.35
    conceded = stats.goals_conceded_pg if stats.goals_conceded_pg is not None else 1.35
    if stats.xg_for_pg is None or stats.xg_against_pg is None:
        return scored, conceded
    w = max(0.0, min(1.0, get_settings().xg_weight))
    return (
        w * stats.xg_for_pg + (1.0 - w) * scored,
        w * stats.xg_against_pg + (1.0 - w) * conceded,
    )


def _predict_football(ctx, home_mult, away_mult, elo_p_home, w, home_edge):
    hs, as_ = ctx.home_stats, ctx.away_stats
    home_scored, home_conceded = scoring_rates(hs)
    away_scored, away_conceded = scoring_rates(as_)
    lam_h, lam_a = poisson.expected_goals(
        home_scored,
        home_conceded,
        away_scored,
        away_conceded,
        home_mult,
        away_mult,
    )
    dc = poisson.derive_markets(poisson.score_matrix(lam_h, lam_a))

    # Keep the Dixon-Coles draw probability; blend the home/away split with Elo.
    p_draw = dc["draw"]
    dc_home_share = dc["home"] / max(dc["home"] + dc["away"], 1e-9)
    home_share = _blend_two_way(dc_home_share, elo_p_home, w, home_edge)
    p_home = home_share * (1.0 - p_draw)
    p_away = (1.0 - home_share) * (1.0 - p_draw)

    markets = [
        _market("match_winner", {"home": p_home, "draw": p_draw, "away": p_away}),
        _market("over_under_2.5", {"over": dc["over_2.5"], "under": dc["under_2.5"]}),
        _market("btts", {"yes": dc["btts_yes"], "no": dc["btts_no"]}),
    ]
    # Show the most likely score consistent with the predicted outcome, not
    # the overall argmax (which is 1-1 for almost any close match).
    score = dc["score_by_outcome"][markets[0].pick]
    return (
        markets,
        f"{score[0]}-{score[1]}",
        lam_h,
        lam_a,
        "dixon-coles-poisson + elo ensemble"
        + (" + xg" if hs.xg_for_pg is not None or as_.xg_for_pg is not None else ""),
    )


def _predict_basketball(ctx, home_mult, away_mult, elo_p_home, w, home_edge):
    hs, as_ = ctx.home_stats, ctx.away_stats
    home_pts, away_pts = basketball.expected_points(
        hs.off_rating or basketball.LEAGUE_AVG_RATING,
        hs.def_rating or basketball.LEAGUE_AVG_RATING,
        as_.off_rating or basketball.LEAGUE_AVG_RATING,
        as_.def_rating or basketball.LEAGUE_AVG_RATING,
        hs.pace or basketball.LEAGUE_AVG_PACE,
        as_.pace or basketball.LEAGUE_AVG_PACE,
        home_mult,
        away_mult,
    )
    model = basketball.derive_markets(home_pts, away_pts)
    p_home = _blend_two_way(model["home"], elo_p_home, w, home_edge)

    markets = [
        _market("match_winner", {"home": p_home, "away": 1.0 - p_home}),
        _market(
            f"total_{model['total_line']}",
            {"over": 0.5, "under": 0.5},
        ),
    ]
    return (
        markets,
        f"{round(home_pts)}-{round(away_pts)}",
        home_pts,
        away_pts,
        "pace-adjusted efficiency + elo ensemble",
    )


def _predict_tennis(ctx, home_mult, away_mult, elo_p_home, w, home_edge):
    hs, as_ = ctx.home_stats, ctx.away_stats
    # Fitness doubts shave points off serve/return performance.
    pa_serve, pa_return = tennis.point_probs(
        (hs.serve_pts_won or tennis.AVG_SERVE_PTS_WON) * (0.96 + 0.04 * home_mult),
        (hs.return_pts_won or tennis.AVG_RETURN_PTS_WON) * (0.96 + 0.04 * home_mult),
        (as_.serve_pts_won or tennis.AVG_SERVE_PTS_WON) * (0.96 + 0.04 * away_mult),
        (as_.return_pts_won or tennis.AVG_RETURN_PTS_WON) * (0.96 + 0.04 * away_mult),
    )
    best_of = ctx.fixture.best_of or 3
    set_p = tennis.set_win_prob(pa_serve, pa_return)
    match_p = tennis.match_win_prob(set_p, best_of)
    p_home = _blend_two_way(match_p, elo_p_home, w, home_edge)

    score_dist = tennis.set_score_distribution(set_p, best_of)
    predicted_score = max(score_dist, key=score_dist.get)

    markets = [
        _market("match_winner", {"home": p_home, "away": 1.0 - p_home}),
        _market("set_score", score_dist),
    ]
    return (
        markets,
        predicted_score,
        None,
        None,
        "serve-model markov chain + elo ensemble",
    )
