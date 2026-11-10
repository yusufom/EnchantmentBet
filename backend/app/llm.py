"""Claude review layer.

For each fixture, Claude reviews the statistical model's output together with
the raw inputs (stats, injuries, candidate news headlines) and returns a
structured verdict: which news items are actually about these teams (fixing
keyword-search false positives), a short written analysis for the card, and a
small bounded adjustment to the win probabilities. The statistical model
remains the backbone — Claude can nudge, never override.

Fails open: any error leaves the statistical prediction untouched.
"""

import asyncio
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .config import get_settings
from .schemas import AIPrediction, FixtureContext, Prediction

logger = logging.getLogger(__name__)

MAX_SHIFT = 0.07  # hard cap on how far Claude may move the win probability
CONCURRENCY = 4

_client: anthropic.AsyncAnthropic | None = None

# Most recent review failure, surfaced into PredictionsResponse.errors so a
# misconfigured key is visible in the UI instead of only in the logs.
last_review_error: str | None = None


class ClaudeReview(BaseModel):
    """Structured verdict Claude returns for one fixture: a review of the
    statistical model's output plus Claude's OWN market picks."""

    relevant_news_indices: list[int] = Field(
        description="Indices of news items genuinely about these two teams or "
        "their players and material to THIS match. Discard items about other "
        "clubs, generic league/competition news, and duplicates."
    )
    probability_shift_home: float = Field(
        ge=-0.07, le=0.07,
        description="Bounded adjustment to the home win probability based on "
        "information the statistical model missed (news, injuries, context). "
        "0 when the model's numbers already reflect everything you see.",
    )
    insight: str = Field(
        description="2-3 sentence analysis of this fixture for the prediction "
        "card: the key factors, in plain language. No hedging boilerplate."
    )

    # --- Claude's own picks. "1" = home, "X" = draw, "2" = away. ---
    winner: Literal["1", "X", "2"] = Field(
        description="Your own match result pick (full time). Basketball: never X."
    )
    double_chance: Literal["1X", "12", "X2"] | None = Field(
        default=None,
        description="Football only: the double-chance combination you would back.",
    )
    over_under_1_5: Literal["over", "under"] | None = Field(
        default=None, description="Football only: total goals vs the 1.5 line."
    )
    over_under_2_5: Literal["over", "under"] | None = Field(
        default=None, description="Football only: total goals vs the 2.5 line."
    )
    btts: Literal["yes", "no"] | None = Field(
        default=None, description="Football only: both teams to score."
    )
    first_half_winner: Literal["1", "X", "2"] | None = Field(
        default=None,
        description="Who leads at half time (X = level; football and basketball).",
    )
    total_points: Literal["over", "under"] | None = Field(
        default=None,
        description="Basketball only: total points vs the model's projected line.",
    )
    pick_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Your overall confidence in your own picks, 0-1.",
    )


def llm_available() -> bool:
    s = get_settings()
    return s.llm_enabled and bool(s.anthropic_api_key)


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        headers = {}
        if settings.anthropic_workspace_id:
            # Identity-linked API keys must state the workspace they act in.
            headers["anthropic-workspace-id"] = settings.anthropic_workspace_id
        _client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, default_headers=headers or None
        )
    return _client


SYSTEM = (
    "You are a sports betting analyst. For each fixture you do two jobs.\n"
    "1) REVIEW the statistical model's output (Dixon-Coles Poisson for "
    "football, pace-adjusted efficiency for basketball, blended with Elo): "
    "filter the news headlines (keyword search includes irrelevant articles) "
    "and apply a small probability adjustment only when the model clearly "
    "missed something. Most fixtures need no adjustment.\n"
    "2) MAKE YOUR OWN PICKS, independently: full-time winner (1/X/2); for "
    "football also double chance, over/under 1.5 goals, over/under 2.5 "
    "goals, both-teams-to-score, and first-half leader; for basketball also "
    "first-half leader and total points vs the model's projected line. Your "
    "picks may disagree with the model — that disagreement is valuable. "
    "Judge only from what is provided plus general sports knowledge."
)


def _stats_line(side: str, stats) -> str:
    parts = [f"{side} stats: rating {stats.rating:.0f}"]
    if stats.goals_scored_pg is not None:
        parts.append(f"scored/pg {stats.goals_scored_pg}")
        parts.append(f"conceded/pg {stats.goals_conceded_pg}")
    if stats.xg_for_pg is not None:
        parts.append(f"xG/pg {stats.xg_for_pg}")
        parts.append(f"xGA/pg {stats.xg_against_pg}")
    if stats.off_rating is not None:
        parts.append(f"off rating {stats.off_rating:.1f}")
        parts.append(f"def rating {stats.def_rating:.1f}")
        parts.append(f"pace {stats.pace}")
    parts.append(f"form {''.join(stats.form) or 'n/a'}")
    return ", ".join(parts) + "."


def _fixture_prompt(ctx: FixtureContext, pred: Prediction) -> str:
    f = ctx.fixture
    main = pred.markets[0]
    draw = f"draw {main.outcomes['draw']:.2f}, " if "draw" in main.outcomes else ""
    lines = [
        f"{f.sport.title()} match: {f.home.name} (home) vs {f.away.name} (away), "
        f"{f.league}, {pred.date}.",
        f"Model probabilities: home {main.outcomes.get('home', 0):.2f}, "
        f"{draw}away {main.outcomes.get('away', 0):.2f}. "
        f"Predicted score {pred.predicted_score}.",
        _stats_line("Home", ctx.home_stats),
        _stats_line("Away", ctx.away_stats),
    ]
    if ctx.injuries:
        lines.append("Injuries: " + "; ".join(
            f"{i.player} ({'home' if i.team_id == ctx.home_stats.competitor_id else 'away'}, "
            f"{i.status}, {i.detail or 'unknown'})"
            for i in ctx.injuries
        ))
    if pred.odds and pred.odds.match_winner:
        mw = pred.odds.match_winner
        lines.append(
            f"Bookmaker odds (vig removed, {pred.odds.bookmakers} book(s)): "
            f"home {mw.get('home',0):.2f}, draw {mw.get('draw',0):.2f}, "
            f"away {mw.get('away',0):.2f}. The market is well informed — treat a "
            "large gap between it and the model as a reason to look harder, not "
            "as an automatic edge."
        )
    if pred.match_facts:
        lines.append("Pre-match facts:")
        lines += [f"  - {mf.label}: {mf.value}" for mf in pred.match_facts]
    if pred.news:
        lines.append("News headlines (numbered, from keyword search — many may be irrelevant):")
        lines += [f"  [{i}] {n.headline} — {n.source or 'unknown'}" for i, n in enumerate(pred.news)]
    else:
        lines.append("News headlines: none.")
    if f.sport == "basketball":
        total_line = next(
            (m.name.replace("total_", "") for m in pred.markets if m.name.startswith("total_")),
            None,
        )
        if total_line:
            lines.append(f"Model's projected total points line: {total_line}.")
        lines.append(
            "Fill winner, first_half_winner and total_points; leave the "
            "football-only markets null."
        )
    else:
        lines.append(
            "Fill winner, double_chance, over_under_1_5, over_under_2_5, "
            "btts and first_half_winner; leave total_points null."
        )
    return "\n".join(lines)


async def _review_one(
    sem: asyncio.Semaphore, ctx: FixtureContext, pred: Prediction
) -> None:
    """Mutates pred in place with Claude's verdict; silent no-op on failure."""
    try:
        async with sem:
            response = await _get_client().with_options(timeout=60.0).messages.parse(
                model=get_settings().llm_model,
                max_tokens=2000,
                system=SYSTEM,
                messages=[{"role": "user", "content": _fixture_prompt(ctx, pred)}],
                output_format=ClaudeReview,
            )
        review: ClaudeReview = response.parsed_output

        pred.news = [
            n for i, n in enumerate(pred.news) if i in set(review.relevant_news_indices)
        ]
        pred.insight = review.insight.strip() or None

        picks = {"winner": review.winner}
        if review.double_chance:
            picks["double_chance"] = review.double_chance
        if review.over_under_1_5:
            picks["over_under_1.5"] = review.over_under_1_5
        if review.over_under_2_5:
            picks["over_under_2.5"] = review.over_under_2_5
        if review.btts:
            picks["btts"] = review.btts
        if review.first_half_winner:
            picks["first_half_winner"] = review.first_half_winner
        if review.total_points:
            picks["total_points"] = review.total_points
        pred.ai = AIPrediction(
            picks=picks,
            confidence=round(review.pick_confidence, 3),
            analysis=pred.insight or "",
            model=get_settings().llm_model,
        )

        main = pred.markets[0]
        shift = max(-MAX_SHIFT, min(MAX_SHIFT, review.probability_shift_home))
        if shift and "home" in main.outcomes and "away" in main.outcomes:
            home = main.outcomes["home"] + shift
            away = main.outcomes["away"] - shift
            if home > 0.01 and away > 0.01:
                main.outcomes["home"] = round(home, 4)
                main.outcomes["away"] = round(away, 4)
                main.pick = max(main.outcomes, key=main.outcomes.get)
                main.pick_probability = round(main.outcomes[main.pick], 4)
        pred.algorithm += " + claude review"
    except Exception as exc:
        global last_review_error
        last_review_error = f"claude review: {exc}"
        logger.warning(
            "claude review failed for %s, keeping statistical prediction: %s",
            pred.fixture_id,
            exc,
        )


async def review_predictions(
    contexts: list[FixtureContext], predictions: list[Prediction]
) -> None:
    """Runs Claude review over a slate; mutates predictions in place."""
    global last_review_error
    last_review_error = None
    if not llm_available() or not predictions:
        return
    sem = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(
        *(_review_one(sem, ctx, pred) for ctx, pred in zip(contexts, predictions))
    )
    reviewed = sum(1 for p in predictions if p.insight)
    logger.info("claude reviewed %d/%d predictions", reviewed, len(predictions))
