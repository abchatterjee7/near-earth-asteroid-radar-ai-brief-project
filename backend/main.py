"""FastAPI backend for the Near-Earth Asteroid Radar.

Run from the project root:  uvicorn backend.main:app --reload
"""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query

from . import db, nasa
from .briefing import generate_briefing


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Asteroid Radar API", version="2.0.0", lifespan=lifespan)


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def _load_window(start: date | None, days: int) -> tuple[date, date, list[dict], str]:
    """Fetch a window (cache first), and save it to SQLite when it came fresh from NASA."""
    start = start or _today()
    end = start + timedelta(days=days - 1)
    rows, source = await nasa.get_window(start, end)
    if source == "nasa":
        db.save_asteroids(rows)
    return start, end, rows, source


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "using_demo_key": nasa.api_key() == "DEMO_KEY",
        "ai_enabled": bool(os.getenv("GROQ_API_KEY")),
    }


@app.get("/asteroids")
async def get_asteroids(
    start_date: date | None = Query(None, description="Defaults to today (UTC)"),
    days: int = Query(7, ge=1, le=7, description="NASA allows at most 7 days"),
):
    start, end, rows, source = await _load_window(start_date, days)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "count": len(rows),
        "source": source,
        "asteroids": rows,
    }


@app.get("/history/daily")
async def history_daily(days: int = Query(30, ge=1, le=365, description="Look-back window")):
    start = _today() - timedelta(days=days)
    end = _today() + timedelta(days=7)  # include upcoming days we have already stored
    return {"days": db.daily_summary(start.isoformat(), end.isoformat())}


@app.get("/history/stats")
async def history_stats():
    return db.stats()


@app.post("/backfill")
async def backfill(weeks: int = Query(4, ge=1, le=8)):
    """Fetch past weeks from NASA into SQLite (one NASA request per week)."""
    today = _today()
    saved = 0
    fetched_weeks = 0
    stopped_early: str | None = None
    for i in range(weeks):
        start = today - timedelta(days=7 * (i + 1))
        end = start + timedelta(days=6)
        try:
            rows, source = await nasa.get_window(start, end)
        except HTTPException as exc:
            stopped_early = str(exc.detail)
            break
        if source == "nasa":
            db.save_asteroids(rows)
        saved += len(rows)
        fetched_weeks += 1
    return {"weeks_fetched": fetched_weeks, "rows_seen": saved, "stopped_early": stopped_early}


@app.post("/briefing")
async def create_briefing(
    start_date: date | None = Query(None, description="Defaults to today (UTC)"),
    days: int = Query(7, ge=1, le=7),
):
    start, end, rows, _ = await _load_window(start_date, days)
    result = await generate_briefing(rows, start.isoformat(), end.isoformat())
    saved = db.save_briefing(
        start.isoformat(), end.isoformat(), result["source"], result["model"], result["text"]
    )
    return {**saved, "note": result["note"]}


@app.get("/briefings")
async def list_briefings(limit: int = Query(10, ge=1, le=50)):
    return {"briefings": db.list_briefings(limit)}