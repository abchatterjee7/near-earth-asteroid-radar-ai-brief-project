# Near-Earth Asteroid Radar AI Brief Project

A small FastAPI + Streamlit project that pulls live asteroid close-approach data
from NASA's NeoWs API, saves it to SQLite, and can write a weekly briefing.

## Features

- **Live radar**: table, size-vs-distance bubble chart, per-day counts, sidebar filters,
  CSV download, and timed auto-refresh (`st.fragment(run_every=...)`)
- **History**: every fresh NASA fetch is stored in SQLite; view daily trends and
  backfill older weeks
- **AI briefing**: short written summary of the selected window, written by a Groq-hosted
  model when `GROQ_API_KEY` is set, otherwise a rule-based summary (no key needed)

## Project layout

```
asteroid_radar/
  backend/
    main.py       FastAPI routes
    nasa.py       NASA client + 10-minute in-memory cache
    parsing.py    flattens NASA's nested JSON
    db.py         SQLite (asteroids + briefings tables)
    briefing.py   AI / rule-based briefing
  frontend/
    app.py        Streamlit UI
  tests/
    test_offline.py
  data/           SQLite file is created here
```

## Setup (Windows, PowerShell)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `NASA_API_KEY` (free at https://api.nasa.gov).
Optionally set `GROQ_API_KEY` (free at https://console.groq.com) for AI briefings.
Values in `.env` can be written with or without quotes; both work.

`GROQ_MODEL` must be a model that exists on Groq. The default is `openai/gpt-oss-20b`.
Groq's model list changes often, so check https://console.groq.com/docs/models.
Do not use OpenAI names such as `gpt-4o-mini`; Groq does not host them.

## Run (two terminals, both from the project folder)

```
# Terminal 1
uvicorn backend.main:app --reload

# Terminal 2
streamlit run frontend/app.py
```

Or double-click `run_backend.bat` and `run_frontend.bat`.

- App: http://localhost:8501
- API docs: http://127.0.0.1:8000/docs

## API endpoints

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/health` | status, whether DEMO_KEY / AI are in use |
| GET | `/asteroids?start_date=&days=` | asteroids for a window (max 7 days); saves fresh data |
| GET | `/history/daily?days=` | per-day summary from SQLite |
| GET | `/history/stats` | totals and date range stored |
| POST | `/backfill?weeks=` | fetch past weeks from NASA into SQLite |
| POST | `/briefing?start_date=&days=` | generate and save a briefing |
| GET | `/briefings?limit=` | past briefings |

## Tests

```
python -m unittest discover -s tests -v
```

These run offline and cover parsing, SQLite, and the rule-based briefing.

## Troubleshooting

- **429 from the backend**: NASA's DEMO_KEY quota is tiny. Use your own key in `.env`.
- **"Can't reach the FastAPI backend"**: start Terminal 1 first.
- **Error about `width="stretch"`**: upgrade Streamlit (`pip install -U streamlit`).
- **AI briefing shows "rule-based"**: check `GROQ_API_KEY` and `GROQ_MODEL` in `.env`; the
  note under the briefing says why the AI call was skipped or failed.
- **Groq 429 / rate limit**: the free tier has per-minute limits. Wait a minute and retry.
- **Never share `.env`** or commit it to git (`.gitignore` already excludes it).
- "Potentially hazardous" is NASA's size-and-orbit category. It is not an impact prediction.

# How it looks, lets see via screenshots.

- Live Radar
![](./screenshots/live-radar.png)

- History
![](./screenshots/history.png)

- AI Briefing and generating projection of next week
![](./screenshots/ai-briefing.png)