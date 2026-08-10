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
from ..providers import get_provider
from ..schemas import SPORTS, Prediction, PredictionsResponse, RefreshMeta, Sport

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
    return PredictionsResponse(date=date, sport=sport or "all", predictions=preds, meta=meta)


async def refresh_predictions(date: str, sport: Sport | None = None) -> PredictionsResponse:
    sports: list[Sport] = [sport] if sport else list(SPORTS)
    results = await asyncio.gather(
        *(_refresh_sport(date, s) for s in sports), return_exceptions=True
    )
    for s, result in zip(sports, results):
        if isinstance(result, BaseException):
            logger.error("refresh failed for %s on %s: %r", s, date, result)
    return await get_predictions(date, sport)


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
