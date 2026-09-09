import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import github
from tests.helpers import fixture

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
CONFIG = {"per_source_cap": 8, "github": {"keywords": ["llm", "agent", "ai", "model", "mcp"]}}


class Parse(unittest.TestCase):
    def test_articles(self):
        rows = github.parse_trending_html(fixture("github_trending_daily.html"))
        self.assertEqual(len(rows), 17)
        first = rows[0]
        self.assertEqual(first["path"], "/ayghri/i-have-adhd")
        self.assertIn("coding agent", first["description"])
        self.assertEqual(first["language"], "Python")
        self.assertEqual(first["stars_today"], 656)
        self.assertEqual(first["stars_total"], 31381)


class Filter(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertTrue(github.is_ai_repo({"path": "/x/y", "description": "A coding agent helper"}, ["agent"]))
        self.assertTrue(github.is_ai_repo({"path": "/x/ai-tools", "description": ""}, ["ai"]))
        self.assertFalse(github.is_ai_repo({"path": "/x/y", "description": "Contains air and mail"}, ["ai"]))


class Collect(unittest.TestCase):
    def test_filtered_and_scored(self):
        with mock.patch("sources.github.fetch", return_value=fixture("github_trending_daily.html")):
            res = github.collect(CONFIG, now=NOW, hours=24)
        items = res["items"]
        self.assertTrue(0 < len(items) <= 8)
        self.assertTrue(all(c["source"] == "github" and c["url"].startswith("https://github.com/") for c in items))
        self.assertIsNone(items[0]["age_hours"])
        self.assertEqual(items[0]["score"], 1.0)
        self.assertEqual(items[0]["engagement"]["stars_today"], max(c["engagement"]["stars_today"] for c in items))

    def test_fetch_error(self):
        with mock.patch("sources.github.fetch", side_effect=github.FetchError("HTTP 503")):
            res = github.collect(CONFIG, now=NOW, hours=24)
        self.assertEqual(res["items"], [])
        self.assertFalse(res["fetched_ok"])
