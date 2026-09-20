import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import youtube
from sources.common import FetchError
from tests.helpers import fixture

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)
SHORTS_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


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


class ChannelVideosParse(unittest.TestCase):
    """The /videos tab replaced feeds/videos.xml, which 404s everywhere since 2026-09-19."""

    def test_parses_uploads_with_relative_age(self):
        items = youtube.parse_channel_videos_html(fixture("youtube_channel_videos_kimflip.html"), "김플립")
        self.assertGreaterEqual(len(items), 10)
        first = items[0]
        self.assertEqual(first["video_id"], "h8nVYAeo2sw")
        self.assertEqual(first["channel"], "김플립")
        self.assertEqual(first["views"], 10000)
        self.assertEqual(first["age_hours"], 13 * 24.0)
        self.assertTrue(all(i["title"] for i in items))

    def test_empty_page(self):
        self.assertEqual(youtube.parse_channel_videos_html("<html></html>"), [])


class ChannelShortsParse(unittest.TestCase):
    def test_parses_shorts_newest_first_without_dates(self):
        items = youtube.parse_channel_shorts_html(fixture("youtube_channel_shorts_kimflip.html"), "김플립")
        self.assertGreaterEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first["video_id"], "htC7_Ay2Qy4")
        self.assertEqual(first["views"], 4000)
        self.assertIsNone(first["age_hours"])
        self.assertIn("limit-reset", first["title"])


class RecentShorts(unittest.TestCase):
    WATCH = '<script>var ytInitialPlayerResponse = {"microformat": {"playerMicroformatRenderer": {"publishDate": "%s"}}};</script>'

    def test_keeps_shorts_inside_the_window_and_stops_at_the_first_old_one(self):
        pages = [fixture("youtube_channel_shorts_kimflip.html"),
                 self.WATCH % "2026-09-16T05:00:00-07:00",   # newest, inside
                 self.WATCH % "2026-09-09T05:00:00-07:00"]   # next, outside: scan stops
        with mock.patch("sources.youtube.fetch", side_effect=pages):
            kept = youtube.recent_shorts("cid", "김플립", SHORTS_NOW, 24, lambda s: None)
        self.assertEqual([k["video_id"] for k in kept], ["htC7_Ay2Qy4"])
        self.assertEqual(kept[0]["published_at"], "2026-09-16T05:00:00-07:00")

    def test_nothing_recent(self):
        pages = [fixture("youtube_channel_shorts_kimflip.html"), self.WATCH % "2026-09-01T05:00:00-07:00"]
        with mock.patch("sources.youtube.fetch", side_effect=pages):
            self.assertEqual(youtube.recent_shorts("cid", "c", SHORTS_NOW, 24, lambda s: None), [])


class Collect(unittest.TestCase):
    CONFIG = {"per_source_cap": 8, "youtube": {"queries": ["AI agents"], "channels": {"김플립": "cid"}}}

    def fake_fetch(self, url, **kw):
        if "results?search_query" in url:
            return fixture("youtube_search_today_en.html")
        if "/videos" in url:
            return fixture("youtube_channel_videos_kimflip.html")
        if "/shorts" in url:
            return fixture("youtube_channel_shorts_kimflip.html")
        if "watch?v=" in url:
            return '<script>var ytInitialPlayerResponse = {"microformat": {"playerMicroformatRenderer": {"publishDate": "2026-09-09T12:00:00+00:00"}}};</script>'
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

    def test_a_shorts_video_can_reach_the_digest(self):
        channels_only = {"per_source_cap": 8, "youtube": {"queries": [], "channels": {"김플립": "cid"}}}
        with mock.patch("sources.youtube.fetch", side_effect=self.fake_fetch):
            res = youtube.collect(channels_only, now=NOW, hours=24, sleep=lambda s: None)
        self.assertTrue(any(c["id"] == "htC7_Ay2Qy4" for c in res["items"]),
                        "the owner's taste Short must be able to arrive")

    def test_fetch_errors_are_recorded_not_raised(self):
        with mock.patch("sources.youtube.fetch", side_effect=FetchError("HTTP 429")):
            res = youtube.collect(self.CONFIG, now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["items"], [])
        self.assertFalse(res["fetched_ok"])
        self.assertIn("search:AI agents", res["notes"]["errors"])

    def test_channel_failures_collapse_into_one_line(self):
        cfg = {"per_source_cap": 8, "youtube": {"queries": [], "channels": {"a": "1", "b": "2"}}}
        with mock.patch("sources.youtube.fetch", side_effect=FetchError("HTTP 404")):
            res = youtube.collect(cfg, now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["notes"]["errors"]["channels"], "HTTP 404 (2 of 2 channels)")


class ShortsAreBestEffort(unittest.TestCase):
    CONFIG = {"per_source_cap": 8, "youtube": {"queries": [], "channels": {"a": "1", "b": "2", "c": "3"}}}

    def test_blocked_shorts_leave_uploads_intact_and_stop_after_one_failure(self):
        calls = []

        def fake(url, **kw):
            calls.append(url)
            if "/videos" in url:
                return fixture("youtube_channel_videos_kimflip.html")
            raise FetchError("network: Tunnel connection failed: 403 Forbidden")

        with mock.patch("sources.youtube.fetch", side_effect=fake):
            res = youtube.collect(self.CONFIG, now=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
                                  hours=24 * 400, sleep=lambda s: None)
        self.assertTrue(res["items"], "uploads still arrive when Shorts are blocked")
        self.assertEqual(len([u for u in calls if "/videos" in u]), 3, "every channel's uploads were tried")
        self.assertEqual(len([u for u in calls if "/shorts" in u]), 1, "Shorts stopped after the first refusal")
        self.assertIn("stopped after", res["notes"]["errors"]["shorts"])
