"""Turn NASA's nested NeoWs feed JSON into flat rows (no third-party imports)."""

from datetime import datetime, timezone


def flatten_feed(raw: dict) -> list[dict]:
    """One flat row per asteroid close approach, sorted by approach time."""
    rows: list[dict] = []
    for day, objects in raw.get("near_earth_objects", {}).items():
        for neo in objects:
            approaches = neo.get("close_approach_data") or []
            if not approaches:
                continue
            approach = approaches[0]
            meters = neo["estimated_diameter"]["meters"]
            d_min = meters["estimated_diameter_min"]
            d_max = meters["estimated_diameter_max"]
            approach_time = datetime.fromtimestamp(
                approach["epoch_date_close_approach"] / 1000, tz=timezone.utc
            )
            rows.append(
                {
                    "id": neo["id"],
                    "name": neo["name"].strip("()"),
                    "date": day,
                    "approach_time": approach_time.isoformat(),
                    "diameter_min_m": round(d_min, 1),
                    "diameter_max_m": round(d_max, 1),
                    "diameter_avg_m": round((d_min + d_max) / 2, 1),
                    "velocity_kms": round(
                        float(approach["relative_velocity"]["kilometers_per_second"]), 2
                    ),
                    "miss_distance_km": round(
                        float(approach["miss_distance"]["kilometers"])
                    ),
                    "miss_distance_lunar": round(
                        float(approach["miss_distance"]["lunar"]), 2
                    ),
                    "hazardous": bool(neo["is_potentially_hazardous_asteroid"]),
                    "sentry": bool(neo.get("is_sentry_object", False)),
                    "magnitude": neo.get("absolute_magnitude_h"),
                    "jpl_url": neo.get("nasa_jpl_url"),
                }
            )
    rows.sort(key=lambda r: r["approach_time"])
    return rows
