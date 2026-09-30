"""Talks to NASA's NeoWs feed and caches results briefly in memory."""

import os
import time
from datetime import date

import httpx
from fastapi import HTTPException

from .parsing import flatten_feed

NEO_FEED_URL = "https://api.nasa.gov/neo/rest/v1/feed"
CACHE_TTL_SECONDS = 600  # 10 minutes

# (start_date, end_date) -> (time_fetched, rows)
_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def api_key() -> str:
    return os.getenv("NASA_API_KEY") or "DEMO_KEY"


async def get_window(start: date, end: date) -> tuple[list[dict], str]:
    """Return (rows, source) where source is 'cache' or 'nasa'."""
    key = (start.isoformat(), end.isoformat())
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1], "cache"

    params = {"start_date": key[0], "end_date": key[1], "api_key": api_key()}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(NEO_FEED_URL, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach NASA: {exc}")

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="NASA rate limit hit. DEMO_KEY is heavily limited - "
            "put your own free key in .env as NASA_API_KEY.",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"NASA returned {resp.status_code}: {resp.text[:200]}",
        )

    rows = flatten_feed(resp.json())
    _cache[key] = (time.time(), rows)
    return rows, "nasa"
