"""Prediction orchestration.

Refreshing is strictly date-scoped: it fetches the slate for one date,
re-predicts it, and replaces only the documents for that (sport, date) pair.
Other dates are never touched.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..config import get_settings
from ..db import get_db
from ..engine import predict_fixture
from ..llm import review_predictions
from ..providers import get_provider
from ..schemas import SPORTS, Prediction, PredictionsResponse, RefreshMeta, Sport
from .results import accuracy_summary

logger = logging.getLogger(__name__)


async def get_predictions(date: str, sport: Sport | None = None) -> PredictionsResponse:
    db = get_db()
    query: dict = {"date": date}
    if sport:
        query["sport"] = sport
    docs = await db.predictions.find(query).to_list(length=500)
    preds = []
    for doc in docs:
        doc.pop("_id", None)
        preds.append(Prediction(**doc))
    preds.sort(key=lambda p: (p.fixture.start_time or datetime.max.replace(tzinfo=timezone.utc)))

    meta_docs = await db.refresh_meta.find(query).to_list(length=10)
    meta = []
    for m in meta_docs:
        m.pop("_id", None)
        meta.append(RefreshMeta(**m))
    return PredictionsResponse(
        date=date,
        sport=sport or "all",
        predictions=preds,
        meta=meta,
        accuracy=accuracy_summary(date, preds),
    )


async def refresh_predictions(date: str, sport: Sport | None = None) -> PredictionsResponse:
    enabled = [s for s in SPORTS if s in get_settings().enabled_sports_list]
    sports: list[Sport] = [sport] if sport else enabled
    if sport is None and (disabled := [s for s in SPORTS if s not in enabled]):
        # A full refresh also clears this date's docs for sports that have
        # since been disabled, so they stop appearing in "all" responses.
        db = get_db()
        await db.predictions.delete_many({"date": date, "sport": {"$in": disabled}})
        await db.refresh_meta.delete_many({"date": date, "sport": {"$in": disabled}})
    results = await asyncio.gather(
        *(_refresh_sport(date, s) for s in sports), return_exceptions=True
    )
    errors: list[str] = []
    for s, result in zip(sports, results):
        if isinstance(result, BaseException):
            logger.error("refresh failed for %s on %s: %r", s, date, result)
            errors.append(f"{s}: {result}")
    from .. import llm
    from ..providers import sportmonks

    if llm.last_review_error:
        errors.append(llm.last_review_error)
    response = await get_predictions(date, sport)
    # Explain silence: a configured odds feed that produced nothing looks
    # broken otherwise.
    football = [p for p in response.predictions if p.sport == "football"]
    if sportmonks.enabled() and football and not any(p.odds for p in football):
        covered = ", ".join(sorted(sportmonks.covered_league_names()))
        errors.append(
            f"No bookmaker odds for this slate — your SportMonks plan covers "
            f"only {covered}, and no fixture today is in those leagues."
        )
    response.errors = errors
    return response


async def _refresh_sport(date: str, sport: Sport) -> int:
    settings = get_settings()
    provider = get_provider(sport, settings)
    contexts = await provider.get_fixture_contexts(date)

    predictions = []
    for ctx in contexts:
        pred = predict_fixture(ctx)
        # Store under the requested date (the query key), even if kickoff
        # falls just past midnight UTC.
        pred.date = date
        predictions.append(pred)

    # Claude layer: news relevance filtering, written analysis, bounded
    # probability adjustment. No-op without an Anthropic key.
    await review_predictions(contexts, predictions)

    db = get_db()
    # Replace only this (sport, date) slice of the collection.
    await db.predictions.delete_many({"sport": sport, "date": date})
    if predictions:
        await db.predictions.insert_many(
            [
                {"_id": f"{sport}:{date}:{p.fixture_id}", **p.model_dump(mode="json")}
                for p in predictions
            ]
        )
    await db.refresh_meta.replace_one(
        {"sport": sport, "date": date},
        RefreshMeta(
            sport=sport,
            date=date,
            refreshed_at=datetime.now(timezone.utc),
            fixtures=len(predictions),
            data_source=provider.data_source,
        ).model_dump(mode="json"),
        upsert=True,
    )
    logger.info("refreshed %d %s predictions for %s", len(predictions), sport, date)
    return len(predictions)
