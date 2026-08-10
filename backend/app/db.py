from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import get_settings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongo_uri)
    return _client[get_settings().mongo_db]


async def ensure_indexes() -> None:
    db = get_db()
    # One prediction per fixture per sport per day — refreshing a date replaces
    # only that day's documents.
    await db.predictions.create_index(
        [("sport", 1), ("date", 1), ("fixture_id", 1)], unique=True
    )
    await db.predictions.create_index([("date", 1)])
    await db.refresh_meta.create_index([("sport", 1), ("date", 1)], unique=True)


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
