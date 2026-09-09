import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import reddit
from tests.helpers import fixture

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
CONFIG = {"per_source_cap": 8, "reddit": {"subreddits": ["ClaudeAI", "LocalLLaMA"], "top_n": 5, "spacing_seconds": 3}}


class Parse(unittest.TestCase):
    def test_entries(self):
        rows = reddit.parse_rss_xml(fixture("reddit_claudeai_hot.rss"))
        self.assertGreaterEqual(len(rows), 1)
        first = rows[0]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["id"], "t3_1vt5drr")
        self.assertEqual(first["author"], "/u/claudeai-perfhub")
        self.assertTrue(first["url"].startswith("https://www.reddit.com/r/ClaudeAI/comments/"))
        self.assertTrue(first["published_at"].startswith("2026-08-20"))
        self.assertNotIn("<", first["snippet"])


class Collect(unittest.TestCase):
    def test_rank_metric_and_spacing(self):
        sleeps = []
        with mock.patch("sources.reddit.fetch", return_value=fixture("reddit_artificial_hot.rss")):
            res = reddit.collect(CONFIG, now=datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc), hours=24, sleep=sleeps.append)
        self.assertEqual(sleeps, [3])
        items = res["items"]
        self.assertTrue(items)
        self.assertEqual(items[0]["engagement"]["rank"], 1)
        self.assertEqual(items[0]["score"], 1.0)
        self.assertTrue(all(c["author"].startswith("r/") for c in items))

    def test_old_posts_are_dropped_beyond_three_windows(self):
        with mock.patch("sources.reddit.fetch", return_value=fixture("reddit_claudeai_hot.rss")):
            res = reddit.collect({"per_source_cap": 8, "reddit": {"subreddits": ["ClaudeAI"], "top_n": 5}}, now=NOW, hours=24, sleep=lambda s: None)
        self.assertFalse(any(c["id"] == "t3_1vt5drr" for c in res["items"]))
