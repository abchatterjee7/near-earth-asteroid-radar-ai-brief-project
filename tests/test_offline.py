"""Offline tests (no network, no API keys). Run from the project root:

    python -m unittest discover -s tests -v
"""

import asyncio
import os
import tempfile
import unittest

# Point the database at a throwaway file BEFORE importing backend.db
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GROQ_API_KEY"] = ""  # force the rule-based briefing path

from backend import briefing, db  # noqa: E402
from backend.parsing import flatten_feed  # noqa: E402


def make_neo(neo_id, name, hazardous, dia_min, dia_max, speed, lunar, epoch_ms):
    return {
        "id": neo_id,
        "name": name,
        "nasa_jpl_url": f"http://example.com/{neo_id}",
        "absolute_magnitude_h": 22.1,
        "is_potentially_hazardous_asteroid": hazardous,
        "is_sentry_object": False,
        "estimated_diameter": {
            "meters": {"estimated_diameter_min": dia_min, "estimated_diameter_max": dia_max}
        },
        "close_approach_data": [
            {
                "epoch_date_close_approach": epoch_ms,
                "relative_velocity": {"kilometers_per_second": str(speed)},
                "miss_distance": {"kilometers": str(lunar * 384400), "lunar": str(lunar)},
            }
        ],
    }


SAMPLE = {
    "near_earth_objects": {
        "2026-09-30": [
            make_neo("1", "(2020 AB)", True, 100.0, 200.0, 12.34, 10.0, 1790000000000),
            make_neo("2", "(2021 CD)", False, 10.0, 20.0, 5.5, 0.8, 1789990000000),
        ],
        "2026-10-01": [
            make_neo("3", "(2022 EF)", False, 50.0, 60.0, 20.1, 25.5, 1790090000000),
        ],
    }
}


class ParsingTests(unittest.TestCase):
    def test_flatten(self):
        rows = flatten_feed(SAMPLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["id"] for r in rows], ["2", "1", "3"])  # sorted by time
        first = rows[1]
        self.assertEqual(first["name"], "2020 AB")
        self.assertEqual(first["diameter_avg_m"], 150.0)
        self.assertTrue(first["hazardous"])
        self.assertEqual(first["miss_distance_lunar"], 10.0)

    def test_empty(self):
        self.assertEqual(flatten_feed({}), [])


class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_save_is_idempotent_and_summarises(self):
        rows = flatten_feed(SAMPLE)
        db.save_asteroids(rows)
        db.save_asteroids(rows)  # same rows again -> no duplicates
        self.assertEqual(db.stats()["total"], 3)

        got = db.get_asteroids("2026-09-30", "2026-10-01")
        self.assertEqual(len(got), 3)
        self.assertIsInstance(got[0]["hazardous"], bool)

        daily = db.daily_summary("2026-09-30", "2026-10-01")
        self.assertEqual([d["date"] for d in daily], ["2026-09-30", "2026-10-01"])
        self.assertEqual(daily[0]["total"], 2)
        self.assertEqual(daily[0]["hazardous"], 1)
        self.assertEqual(daily[0]["closest_lunar"], 0.8)

    def test_briefings(self):
        saved = db.save_briefing("2026-09-30", "2026-10-06", "rule-based", None, "hello")
        self.assertIn("id", saved)
        self.assertEqual(db.list_briefings(1)[0]["text"], "hello")


class BriefingTests(unittest.TestCase):
    def test_rule_based_when_no_key(self):
        rows = flatten_feed(SAMPLE)
        result = asyncio.run(briefing.generate_briefing(rows, "2026-09-30", "2026-10-06"))
        self.assertEqual(result["source"], "rule-based")
        self.assertIn("3 near-Earth asteroid", result["text"])
        self.assertIn("2021 CD", result["text"])  # the closest pass
        self.assertIsNotNone(result["note"])

    def test_empty_window(self):
        result = asyncio.run(briefing.generate_briefing([], "2026-09-30", "2026-10-06"))
        self.assertIn("No near-Earth", result["text"])


if __name__ == "__main__":
    unittest.main()