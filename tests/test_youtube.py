import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import youtube
from tests.helpers import fixture

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)


class SearchParse(unittest.TestCase):
    def test_parses_videos_with_age_and_views(self):
        items = youtube.parse_search_html(fixture("youtube_search_today_en.html"))
        self.assertGreaterEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first["video_id"], "6AuYLbHqirk")
        self.assertEqual(first["channel"], "IBM Technology")
        self.assertEqual(first["age_hours"], 9.0)
        self.assertEqual(first["views"], 12041)
        self.assertTrue(all(i["video_id"] and i["title"] for i in items))

    def test_no_initial_data_gives_empty_list(self):
        self.assertEqual(youtube.parse_search_html("<html></html>"), [])


class RssParse(unittest.TestCase):
    def test_parses_channel_feed(self):
        items = youtube.parse_rss_xml(fixture("youtube_channel_rss_anthropic.xml"))
        self.assertEqual(len(items), 15)
        self.assertEqual(items[0]["channel"], "Anthropic")
        self.assertTrue(items[0]["published_at"].startswith("2026-09-01T19:21"))
        self.assertIsInstance(items[0]["views"], int)
        self.assertGreater(items[0]["views"], 0)
        self.assertTrue(all(len(i["video_id"]) == 11 for i in items))


class Collect(unittest.TestCase):
    CONFIG = {"per_source_cap": 8, "youtube": {"queries": ["AI agents"], "channels": {"Anthropic": "UCrDwWp7EBBv4NwvScIpBDOA"}}}

    def fake_fetch(self, url, **kw):
        if "results?search_query" in url:
            return fixture("youtube_search_today_en.html")
        if "feeds/videos.xml" in url:
            return fixture("youtube_channel_rss_anthropic.xml")
        raise AssertionError("unexpected url " + url)

    def test_window_scores_and_cap(self):
        with mock.patch("sources.youtube.fetch", side_effect=self.fake_fetch):
            res = youtube.collect(self.CONFIG, now=NOW, hours=24, sleep=lambda s: None)
        items = res["items"]
        self.assertTrue(res["fetched_ok"])
        self.assertTrue(0 < len(items) <= 8)
        self.assertTrue(all(c["source"] == "youtube" and c["age_hours"] <= 24 for c in items))
        self.assertEqual(items[0]["score"], 1.0)
        self.assertTrue(all(c["url"].startswith("https://www.youtube.com/watch?v=") for c in items))
        rss_ids = {r["video_id"] for r in youtube.parse_rss_xml(fixture("youtube_channel_rss_anthropic.xml"))}
        for c in items:
            if c["id"] in rss_ids:
                self.assertRegex(c["published_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_fetch_errors_are_recorded_not_raised(self):
        with mock.patch("sources.youtube.fetch", side_effect=youtube.FetchError("HTTP 429")):
            res = youtube.collect(self.CONFIG, now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["items"], [])
        self.assertFalse(res["fetched_ok"])
        self.assertIn("search:AI agents", res["notes"]["errors"])
