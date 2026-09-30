"""Streamlit frontend for the Near-Earth Asteroid Radar.

Run from the project root:  streamlit run frontend/app.py
"""

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
REFRESH_OPTIONS = {"1 minute": 60, "5 minutes": 300, "15 minutes": 900}
SORT_OPTIONS = {
    "Approach time": "approach_time",
    "Miss distance": "miss_distance_lunar",
    "Size": "diameter_avg_m",
    "Speed": "velocity_kms",
}

st.set_page_config(page_title="Asteroid Radar", page_icon="☄️", layout="wide")

# ----------------------------------------------------------------

import sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "backend" imports work


@st.cache_resource  # runs once per server process, not on every rerun
def start_embedded_backend():
    import uvicorn
    from backend.main import app as api_app

    server = uvicorn.Server(
        uvicorn.Config(api_app, host="127.0.0.1", port=8000, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):  # wait up to ~10s for it to come up
        try:
            requests.get("http://127.0.0.1:8000/health", timeout=1)
            return
        except requests.exceptions.RequestException:
            time.sleep(0.2)


if os.getenv("EMBED_BACKEND") == "1":  # only on the cloud; local dev is unchanged
    start_embedded_backend()

# ---------------------------------------------------------------- helpers
class ApiError(Exception):
    """Raised when the FastAPI backend can't be reached or returns an error."""


def call_api(method: str, path: str, **params):
    try:
        resp = requests.request(method, f"{API_URL}{path}", params=params, timeout=90)
    except requests.exceptions.ConnectionError:
        raise ApiError(
            "Can't reach the FastAPI backend. Start it from the project folder with "
            "`uvicorn backend.main:app --reload`."
        )
    except requests.exceptions.RequestException as exc:
        raise ApiError(f"Request failed: {exc}")
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"Backend error ({resp.status_code}): {detail}")
    return resp.json()


def rows_to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if not df.empty:
        df["approach_time"] = pd.to_datetime(df["approach_time"])
        df["hazard_label"] = df["hazardous"].map(
            {True: "Hazardous", False: "Not hazardous"}
        )
    return df


# ---------------------------------------------------------------- sidebar
st.title("☄️ Near-Earth Asteroid Radar")
st.caption(
    "Live data from NASA's NeoWs API through a FastAPI backend, saved to SQLite. "
    "1 LD (lunar distance) = the average Earth-Moon distance, about 384,400 km."
)
st.markdown(
        """
        <div style="margin-top: -0.75rem; margin-bottom: 1.5rem; line-height: 1.35;">
            <div style="margin-top: 0.15rem; color: var(--text-color); opacity: 0.65; font-size: 0.875rem;">
                Developed by:
                <a href="https://www.linkedin.com/in/abchatterjee7" target="_blank" rel="noopener noreferrer">
                    Aaditya B Chatterjee
                </a>
            </div>
        </div>
        """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Time window")
    start = st.date_input("Start date (UTC)", value=datetime.now(timezone.utc).date())
    days = st.slider("Number of days", 1, 7, 7)

    st.header("Filters")
    hazard_only = st.checkbox("Potentially hazardous only")
    max_ld = st.slider("Max miss distance (LD)", 0.5, 200.0, 200.0)
    min_size = st.number_input("Min size (metres)", min_value=0, value=0, step=10)
    sort_label = st.selectbox("Sort table by", list(SORT_OPTIONS))

    st.header("Auto-refresh")
    auto_refresh = st.toggle("Refresh live radar automatically", value=True)
    refresh_label = st.selectbox(
        "Refresh every", list(REFRESH_OPTIONS), index=1, disabled=not auto_refresh
    )

start_iso = start.isoformat()
run_every = REFRESH_OPTIONS[refresh_label] if auto_refresh else None


# ---------------------------------------------------------------- live radar
# Only this function re-runs on the timer, so the tabs around it stay put.
@st.fragment(run_every=run_every)
def live_radar(start_iso, days, hazard_only, max_ld, min_size, sort_key):
    try:
        payload = call_api("GET", "/asteroids", start_date=start_iso, days=days)
    except ApiError as exc:
        st.error(str(exc))
        return

    df = rows_to_df(payload["asteroids"])
    if df.empty:
        st.info("NASA returned no asteroids for this window.")
        return

    fdf = df[(df["miss_distance_lunar"] <= max_ld) & (df["diameter_avg_m"] >= min_size)]
    if hazard_only:
        fdf = fdf[fdf["hazardous"]]
    if fdf.empty:
        st.warning("No asteroids match these filters. Try loosening them.")
        return
    fdf = fdf.sort_values(sort_key, ascending=sort_key in ("approach_time", "miss_distance_lunar"))

    closest = fdf.loc[fdf["miss_distance_lunar"].idxmin()]
    fastest = fdf.loc[fdf["velocity_kms"].idxmax()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asteroids", len(fdf))
    c2.metric("Potentially hazardous", int(fdf["hazardous"].sum()))
    c3.metric("Closest pass", f"{closest['miss_distance_lunar']:.2f} LD", closest["name"])
    c4.metric("Fastest", f"{fastest['velocity_kms']:.1f} km/s", fastest["name"])

    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    where = "NASA (fresh, saved to history)" if payload["source"] == "nasa" else "backend cache"
    st.caption(f"Last updated {now} UTC · source: {where}")

    left, right = st.columns(2)
    with left:
        fig = px.scatter(
            fdf,
            x="miss_distance_lunar",
            y="diameter_avg_m",
            size="velocity_kms",
            color="hazard_label",
            hover_name="name",
            hover_data={"velocity_kms": ":.1f", "approach_time": True, "hazard_label": False},
            log_x=True,
            log_y=True,
            size_max=30,
            color_discrete_map={"Hazardous": "#ef4444", "Not hazardous": "#3b82f6"},
            labels={
                "miss_distance_lunar": "Miss distance (LD, log)",
                "diameter_avg_m": "Avg diameter (m, log)",
                "velocity_kms": "Speed (km/s)",
                "hazard_label": "",
            },
            title="Size vs miss distance (bubble = speed)",
        )
        fig.add_vline(x=1, line_dash="dash", line_color="gray", annotation_text="Moon")
        st.plotly_chart(fig)
    with right:
        per_day = fdf.groupby(["date", "hazard_label"]).size().unstack(fill_value=0)
        st.markdown("**Approaches per day**")
        st.bar_chart(per_day)

    st.dataframe(
        fdf[
            [
                "name",
                "approach_time",
                "diameter_avg_m",
                "velocity_kms",
                "miss_distance_lunar",
                "miss_distance_km",
                "hazardous",
                "jpl_url",
            ]
        ],
        column_config={
            "name": "Asteroid",
            "approach_time": st.column_config.DatetimeColumn(
                "Closest approach (UTC)", format="D MMM, HH:mm"
            ),
            "diameter_avg_m": st.column_config.NumberColumn("Avg size (m)", format="%.0f"),
            "velocity_kms": st.column_config.ProgressColumn(
                "Speed (km/s)",
                min_value=0,
                max_value=float(df["velocity_kms"].max()),
                format="%.1f",
            ),
            "miss_distance_lunar": st.column_config.NumberColumn(
                "Miss distance (LD)", format="%.2f"
            ),
            "miss_distance_km": st.column_config.NumberColumn(
                "Miss distance (km)", format="%d"
            ),
            "hazardous": st.column_config.CheckboxColumn("Hazardous?"),
            "jpl_url": st.column_config.LinkColumn("JPL page", display_text="Open"),
        },
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Download CSV",
        fdf.to_csv(index=False).encode("utf-8"),
        file_name="asteroids.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------- history
def render_history():
    if msg := st.session_state.pop("backfill_msg", None):
        st.success(msg)

    lookback = st.slider("Look back (days)", 7, 90, 30)
    try:
        stats = call_api("GET", "/history/stats")
        daily = call_api("GET", "/history/daily", days=lookback)
    except ApiError as exc:
        st.error(str(exc))
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Stored close approaches", stats["total"])
    m2.metric("Days covered", stats["days_covered"])
    m3.metric("Latest stored date", stats["last_date"] or "-")

    with st.expander("Backfill older weeks from NASA"):
        st.caption(
            "Uses one NASA request per week. DEMO_KEY has a very small quota, so "
            "add your own free key in .env before backfilling many weeks."
        )
        weeks = st.slider("Weeks to fetch", 1, 8, 4)
        if st.button("Backfill history"):
            with st.spinner("Fetching from NASA..."):
                try:
                    result = call_api("POST", "/backfill", weeks=weeks)
                except ApiError as exc:
                    st.error(str(exc))
                else:
                    text = (
                        f"Fetched {result['weeks_fetched']} week(s), "
                        f"{result['rows_seen']} close approaches."
                    )
                    if result["stopped_early"]:
                        text += f" Stopped early: {result['stopped_early']}"
                    st.session_state["backfill_msg"] = text
                    st.rerun()

    if not daily["days"]:
        st.info(
            "No history yet. Open the Live radar tab (each fresh NASA fetch is saved), "
            "or use the backfill above."
        )
        return

    df = pd.DataFrame(daily["days"])
    df["date"] = pd.to_datetime(df["date"])
    df["hazardous"] = df["hazardous"].fillna(0).astype(int)
    df["not_hazardous"] = df["total"] - df["hazardous"]

    st.markdown("**Approaches per day**")
    st.bar_chart(df.set_index("date")[["not_hazardous", "hazardous"]])
    st.markdown("**Closest approach per day (LD)**")
    st.line_chart(df.set_index("date")["closest_lunar"])
    st.dataframe(
        df[["date", "total", "hazardous", "closest_lunar", "largest_m", "fastest_kms"]],
        column_config={
            "date": st.column_config.DateColumn("Date", format="D MMM YYYY"),
            "total": "Approaches",
            "hazardous": "Hazardous",
            "closest_lunar": st.column_config.NumberColumn("Closest (LD)", format="%.2f"),
            "largest_m": st.column_config.NumberColumn("Largest (m)", format="%.0f"),
            "fastest_kms": st.column_config.NumberColumn("Fastest (km/s)", format="%.1f"),
        },
        hide_index=True,
        width="stretch",
    )


# ---------------------------------------------------------------- AI briefing
def render_briefing(start_iso: str, days: int):
    st.write(
        f"Generate a short written briefing for the time window selected in the "
        f"sidebar ({start_iso}, {days} day{'s' if days != 1 else ''})."
    )
    try:
        health = call_api("GET", "/health")
    except ApiError as exc:
        st.error(str(exc))
        return
    if not health["ai_enabled"]:
        st.info(
            "No GROQ_API_KEY found in .env, so the briefing will be a simple "
            "rule-based summary. Add a key to get AI-written text."
        )

    if st.button("Generate briefing", type="primary"):
        with st.spinner("Writing briefing..."):
            try:
                st.session_state["briefing"] = call_api(
                    "POST", "/briefing", start_date=start_iso, days=days
                )
            except ApiError as exc:
                st.error(str(exc))

    result = st.session_state.get("briefing")
    if result:
        with st.container(border=True):
            st.markdown(result["text"])
            who = f"AI ({result['model']})" if result["source"] == "ai" else "rule-based"
            st.caption(f"{result['start_date']} to {result['end_date']} · written by {who}")
        if result.get("note"):
            st.warning(result["note"])

    with st.expander("Past briefings"):
        try:
            past = call_api("GET", "/briefings", limit=10)["briefings"]
        except ApiError as exc:
            st.error(str(exc))
            return
        if not past:
            st.caption("Nothing saved yet.")
        for b in past:
            st.markdown(f"**{b['start_date']} to {b['end_date']}** · {b['source']} · {b['created_at']}")
            st.write(b["text"])
            st.divider()


# ---------------------------------------------------------------- layout
tab_live, tab_history, tab_ai = st.tabs(["📡 Live radar", "🗄️ History", "📝 AI briefing"])

with tab_live:
    live_radar(start_iso, days, hazard_only, max_ld, min_size, SORT_OPTIONS[sort_label])
with tab_history:
    render_history()
with tab_ai:
    render_briefing(start_iso, days)