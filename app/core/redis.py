import redis.asyncio as redis
from fastapi import HTTPException, Request

from app.core.config import settings

_client = None


async def get_redis():
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def check_rate_limit(key: str, limit: int, window: int) -> None:
    r = await get_redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")


async def blacklist_token(token: str, ttl_seconds: int) -> None:
    r = await get_redis()
    await r.setex(f"blacklist:{token}", ttl_seconds, "1")


async def is_token_blacklisted(token: str) -> bool:
    r = await get_redis()
    return await r.exists(f"blacklist:{token}") == 1
