import re

from fastapi import APIRouter, HTTPException, Query

from ..schemas import PredictionsResponse, RefreshRequest, Sport
from ..services import predictions as service

router = APIRouter(prefix="/api", tags=["predictions"])

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(date: str) -> str:
    if not DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    return date


@router.get("/predictions", response_model=PredictionsResponse)
async def get_predictions(
    date: str = Query(..., description="YYYY-MM-DD"),
    sport: Sport | None = Query(None),
):
    return await service.get_predictions(_validate_date(date), sport)


@router.post("/predictions/refresh", response_model=PredictionsResponse)
async def refresh_predictions(body: RefreshRequest):
    return await service.refresh_predictions(_validate_date(body.date), body.sport)


@router.get("/health")
async def health():
    return {"status": "ok"}
