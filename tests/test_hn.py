import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import hn
from tests.helpers import fixture

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
CONFIG = {"per_source_cap": 8, "hn": {"keywords": ["AI"], "min_points": 50}}


class Parse(unittest.TestCase):
    def test_hits(self):
        hits = hn.parse_hits(fixture("hn_algolia_ai_24h.json"))
        self.assertGreaterEqual(len(hits), 3)
        first = hits[0]
        self.assertEqual(first["id"], "49610538")
        self.assertTrue(first["title"].startswith("LibreOffice breaks download records"))
        self.assertEqual(first["points"], 672)
        self.assertTrue(first["url"].startswith("https://"))

    def test_story_without_url_links_to_hn(self):
        hits = hn.parse_hits('{"hits": [{"objectID": "1", "title": "t", "points": 9, "num_comments": 0, "created_at": "2026-09-09T00:00:00Z", "author": "a"}]}')
        self.assertEqual(hits[0]["url"], "https://news.ycombinator.com/item?id=1")


class Collect(unittest.TestCase):
    def test_window_and_scores(self):
        with mock.patch("sources.hn.fetch", return_value=fixture("hn_algolia_ai_24h.json")) as f:
            res = hn.collect(CONFIG, now=NOW, hours=24, sleep=lambda s: None)
        self.assertIn("numericFilters=created_at_i%3E", f.call_args[0][0])
        items = res["items"]
        self.assertTrue(0 < len(items) <= 8)
        self.assertEqual(items[0]["engagement"]["points"], 672)
        self.assertEqual(items[0]["score"], 1.0)
        self.assertTrue(all(c["age_hours"] <= 24 for c in items))
        self.assertIn("HN: https://news.ycombinator.com/item?id=", items[0]["snippet"])

    def test_bad_json_recorded(self):
        with mock.patch("sources.hn.fetch", return_value="not json"):
            res = hn.collect(CONFIG, now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["items"], [])
        self.assertIn("AI", res["notes"]["errors"])
