"""Weekly briefing: written by a Groq-hosted model when a key is set, rule-based otherwise."""

import json
import os
import re

# Groq is retiring llama-3.1-8b-instant and llama-3.3-70b-versatile on the free tier,
# so we default to a gpt-oss model. Override with GROQ_MODEL in .env.
# Current list: https://console.groq.com/docs/models
DEFAULT_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = (
    "You write short, calm, factual briefings about near-Earth asteroid close "
    "approaches for a general audience. Use only the data you are given and never "
    "invent numbers. 'Potentially hazardous' is NASA's technical classification for "
    "large objects whose orbits can come close to Earth's orbit; it is not a "
    "prediction of impact, and you should say so if any are listed. 1 LD (lunar "
    "distance) is the average Earth-Moon distance, about 384,400 km. Avoid hype."
)


def build_facts(rows: list[dict]) -> dict:
    """Boil the rows down to a small summary (keeps the AI prompt tiny and cheap)."""

    def slim(r: dict) -> dict:
        return {
            k: r[k]
            for k in (
                "name",
                "date",
                "diameter_avg_m",
                "velocity_kms",
                "miss_distance_lunar",
                "hazardous",
            )
        }

    per_day: dict[str, int] = {}
    for r in rows:
        per_day[r["date"]] = per_day.get(r["date"], 0) + 1

    return {
        "total": len(rows),
        "hazardous_count": sum(1 for r in rows if r["hazardous"]),
        "sentry_count": sum(1 for r in rows if r.get("sentry")),
        "closest": [slim(r) for r in sorted(rows, key=lambda r: r["miss_distance_lunar"])[:3]],
        "largest": [slim(r) for r in sorted(rows, key=lambda r: -r["diameter_avg_m"])[:3]],
        "fastest": [slim(r) for r in sorted(rows, key=lambda r: -r["velocity_kms"])[:3]],
        "per_day": dict(sorted(per_day.items())),
    }


def rule_based_briefing(facts: dict, start: str, end: str) -> str:
    if not facts["total"]:
        return f"No near-Earth asteroid close approaches were listed for {start} to {end}."
    closest = facts["closest"][0]
    largest = facts["largest"][0]
    fastest = facts["fastest"][0]
    busiest_day = max(facts["per_day"], key=facts["per_day"].get)
    return (
        f"Between {start} and {end}, NASA lists {facts['total']} near-Earth asteroid "
        f"close approaches, {facts['hazardous_count']} of them classed as potentially "
        f"hazardous (a size-and-orbit category, not an impact forecast).\n\n"
        f"The closest pass is {closest['name']} on {closest['date']} at "
        f"{closest['miss_distance_lunar']:.2f} lunar distances. The largest is "
        f"{largest['name']} at roughly {largest['diameter_avg_m']:.0f} m across, and the "
        f"fastest is {fastest['name']} at {fastest['velocity_kms']:.1f} km/s. "
        f"{busiest_day} is the busiest day with {facts['per_day'][busiest_day]} approaches."
    )


async def generate_briefing(rows: list[dict], start: str, end: str) -> dict:
    """Returns {text, source, model, note}. Never raises: falls back to rules."""
    facts = build_facts(rows)
    fallback = rule_based_briefing(facts, start, end)

    if not facts["total"]:
        return {"text": fallback, "source": "rule-based", "model": None, "note": None}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {
            "text": fallback,
            "source": "rule-based",
            "model": None,
            "note": "Set GROQ_API_KEY in .env to get AI-written briefings.",
        }

    model = os.getenv("GROQ_MODEL") or DEFAULT_MODEL
    user_prompt = (
        f"Write a briefing for {start} to {end}. Use two short paragraphs (about 150 "
        "words total), then a final line starting with 'Watch list:' naming up to "
        "three objects worth a look and why.\n\nData:\n"
        + json.dumps(facts, indent=2)
    )

    try:
        from groq import AsyncGroq  # imported here so the app runs without it

        client = AsyncGroq(api_key=api_key)

        extra = {}
        if "gpt-oss" in model:
            # gpt-oss models "think" first; keep that short so the answer isn't cut off
            extra["reasoning_effort"] = "low"

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_completion_tokens=1500,
            **extra,
        )
        text = (response.choices[0].message.content or "").strip()
        # some reasoning models wrap their thinking in <think> tags; remove it
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text:
            raise ValueError("model returned an empty answer")
        return {"text": text, "source": "ai", "model": model, "note": None}
    except Exception as exc:  # any failure -> still give the user a briefing
        return {
            "text": fallback,
            "source": "rule-based",
            "model": None,
            "note": (
                f"AI briefing failed ({type(exc).__name__}: {str(exc)[:160]}). "
                "Showing the rule-based summary. Check GROQ_MODEL in .env."
            ),
        }