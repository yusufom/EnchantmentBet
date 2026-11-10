"""Result fetching, grading, and day-level accuracy.

Grades each stored prediction against the final score: the main pick,
over/under 2.5, both-teams-to-score, and the exact scoreline. Accuracy for a
date is computed from the stored grades on read.
"""

import logging
from datetime import datetime, timezone

from ..config import get_settings
from ..db import get_db
from ..providers import get_provider
from ..schemas import (
    SPORTS,
    AccuracySummary,
    ConfidenceBucket,
    FixtureResult,
    MarketGrade,
    Prediction,
    PredictionsResponse,
    Sport,
)

logger = logging.getLogger(__name__)


def _outcome(home: int, away: int) -> str:
    return "home" if home > away else "away" if away > home else "draw"


SYMBOL = {"home": "1", "draw": "X", "away": "2"}


def _grade_ai(pred: Prediction, home: int, away: int,
              ht_home: int | None, ht_away: int | None) -> list[MarketGrade]:
    if not pred.ai:
        return []
    total = home + away
    actuals: dict[str, str | None] = {
        "winner": SYMBOL[_outcome(home, away)],
        "over_under_1.5": "over" if total > 1.5 else "under",
        "over_under_2.5": "over" if total > 2.5 else "under",
        "btts": "yes" if home > 0 and away > 0 else "no",
    }
    if ht_home is not None and ht_away is not None:
        actuals["first_half_winner"] = SYMBOL[_outcome(ht_home, ht_away)]
    total_line = next(
        (m.name.replace("total_", "") for m in pred.markets if m.name.startswith("total_")),
        None,
    )
    if total_line:
        actuals["total_points"] = "over" if total > float(total_line) else "under"

    grades = []
    for market, pick in pred.ai.picks.items():
        if market == "double_chance":
            actual = SYMBOL[_outcome(home, away)]
            grades.append(MarketGrade(
                market=market, pick=pick, actual=actual, correct=actual in pick
            ))
            continue
        actual = actuals.get(market)
        if actual is not None:
            grades.append(MarketGrade(
                market=market, pick=pick, actual=actual, correct=pick == actual
            ))
    return grades


def grade_prediction(pred: Prediction, res: dict) -> Prediction:
    home, away, status = res["home"], res["away"], res["status"]
    ht_home, ht_away = res.get("ht_home"), res.get("ht_away")
    outcome = _outcome(home, away)
    pred.result = FixtureResult(
        home_score=home,
        away_score=away,
        status=status,
        outcome=outcome,
        ht_home=ht_home,
        ht_away=ht_away,
        fetched_at=datetime.now(timezone.utc),
    )
    grades: list[MarketGrade] = []
    for market in pred.markets:
        if market.name == "match_winner":
            grades.append(MarketGrade(
                market=market.name, pick=market.pick, actual=outcome,
                correct=market.pick == outcome,
            ))
        elif market.name.startswith("over_under_"):
            line = float(market.name.replace("over_under_", ""))
            actual = "over" if home + away > line else "under"
            grades.append(MarketGrade(
                market=market.name, pick=market.pick, actual=actual,
                correct=market.pick == actual,
            ))
        elif market.name == "btts":
            actual = "yes" if home > 0 and away > 0 else "no"
            grades.append(MarketGrade(
                market=market.name, pick=market.pick, actual=actual,
                correct=market.pick == actual,
            ))
    # Exact scorelines are only a meaningful market in football; a basketball
    # score is never predicted exactly and would just drag the stat to 0%.
    if pred.predicted_score and pred.sport == "football":
        grades.append(MarketGrade(
            market="exact_score", pick=pred.predicted_score, actual=f"{home}-{away}",
            correct=pred.predicted_score == f"{home}-{away}",
        ))
    pred.grades = grades
    pred.ai_grades = _grade_ai(pred, home, away, ht_home, ht_away)
    pred.pick_correct = next(
        (g.correct for g in grades if g.market == "match_winner"), None
    )
    return pred


def accuracy_summary(date: str, predictions: list[Prediction]) -> AccuracySummary | None:
    graded = [p for p in predictions if p.result is not None]
    if not graded:
        return None
    summary = AccuracySummary(date=date, graded=len(graded), total=len(predictions))

    picks = [p.pick_correct for p in graded if p.pick_correct is not None]
    if picks:
        summary.pick_accuracy = round(sum(picks) / len(picks), 3)

    # Same picks, split by the confidence they were made with. Reported in a
    # fixed high -> low order so the bands read as a calibration curve.
    by_confidence: dict[str, list[bool]] = {}
    for p in graded:
        if p.pick_correct is not None:
            by_confidence.setdefault(p.confidence_label, []).append(p.pick_correct)
    summary.confidence_accuracy = {
        label: ConfidenceBucket(
            graded=len(vals),
            accuracy=round(sum(vals) / len(vals), 3),
        )
        for label in ("high", "medium", "low")
        if (vals := by_confidence.get(label))
    }

    by_market: dict[str, list[bool]] = {}
    for p in graded:
        for g in p.grades:
            by_market.setdefault(g.market, []).append(g.correct)
    exact = by_market.pop("exact_score", None)
    by_market.pop("match_winner", None)  # already reported as pick_accuracy
    summary.market_accuracy = {
        market: round(sum(vals) / len(vals), 3) for market, vals in by_market.items()
    }
    if exact:
        summary.exact_score_accuracy = round(sum(exact) / len(exact), 3)

    ai_by_market: dict[str, list[bool]] = {}
    for p in graded:
        for g in p.ai_grades:
            ai_by_market.setdefault(g.market, []).append(g.correct)
    if ai_by_market:
        all_ai = [v for vals in ai_by_market.values() for v in vals]
        summary.ai_overall = round(sum(all_ai) / len(all_ai), 3)
        summary.ai_accuracy = {
            market: round(sum(vals) / len(vals), 3)
            for market, vals in ai_by_market.items()
        }
    return summary


async def refresh_results(date: str, sport: Sport | None = None) -> PredictionsResponse:
    from . import predictions as prediction_service

    settings = get_settings()
    enabled = [s for s in SPORTS if s in settings.enabled_sports_list]
    sports: list[Sport] = [sport] if sport else enabled
    db = get_db()
    errors: list[str] = []

    for s in sports:
        docs = await db.predictions.find({"sport": s, "date": date}).to_list(length=500)
        if not docs:
            continue
        try:
            results = await get_provider(s, settings).get_results(date)
        except Exception as exc:
            logger.exception("failed to fetch %s results for %s", s, date)
            errors.append(f"{s} results: {exc}")
            continue
        graded = 0
        for doc in docs:
            res = results.get(doc["fixture_id"])
            if not res:
                continue
            doc.pop("_id", None)
            pred = grade_prediction(Prediction(**doc), res)
            await db.predictions.update_one(
                {"sport": s, "date": date, "fixture_id": pred.fixture_id},
                {"$set": {
                    "result": pred.result.model_dump(mode="json"),
                    "grades": [g.model_dump() for g in pred.grades],
                    "ai_grades": [g.model_dump() for g in pred.ai_grades],
                    "pick_correct": pred.pick_correct,
                }},
            )
            graded += 1
        logger.info("graded %d/%d %s predictions for %s", graded, len(docs), s, date)

    response = await prediction_service.get_predictions(date, sport)
    response.errors = errors
    return response
