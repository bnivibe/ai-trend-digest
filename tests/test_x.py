import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from sources import x
from sources.common import FetchError
from tests.helpers import fixture

NOW = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)


class TimelineParse(unittest.TestCase):
    def test_keeps_originals_only(self):
        rows = x.parse_timeline_html(fixture("x_timeline_fresh_anthropicai.html"))
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all(r["handle"] == "AnthropicAI" for r in rows))
        self.assertFalse(any(r["text"].startswith("RT @") for r in rows))
        self.assertEqual(rows[0]["created_at"].tzinfo, timezone.utc)
        texts = [r["text"] for r in rows]
        self.assertTrue(any(t.startswith("We’re sharing our alignment assessment") for t in texts))
        self.assertFalse(any(t.startswith("We previously described") for t in texts))

    def test_no_next_data_gives_empty_list(self):
        self.assertEqual(x.parse_timeline_html("<html></html>"), [])


class TweetParse(unittest.TestCase):
    def test_tweet_result_json(self):
        row = x.parse_tweet_json(fixture("x_tweet_result.json"))
        self.assertEqual(row["id"], "2079195918595764300")
        self.assertEqual(row["handle"], "RobinhoodApp")
        self.assertEqual(row["likes"], 8725)
        self.assertEqual(row["created_at"].date().isoformat(), "2026-07-20")


class Collect(unittest.TestCase):
    def config(self, accounts):
        return {"per_source_cap": 8, "x": {"accounts": accounts, "min_likes": 100, "stale_days": 7, "spacing_seconds": 1.5}}

    def test_fresh_account_yields_window_items(self):
        with mock.patch("sources.x.fetch", return_value=fixture("x_timeline_fresh_anthropicai.html")):
            res = x.collect(self.config(["AnthropicAI"]), now=NOW, hours=24, sleep=lambda s: None)
        items = res["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["engagement"]["likes"], 10015)
        self.assertEqual(items[0]["score"], 1.0)
        self.assertEqual(items[0]["author"], "@AnthropicAI")
        self.assertRegex(items[0]["url"], r"^https://x\.com/AnthropicAI/status/\d+$")
        self.assertEqual(res["notes"]["stale"], [])

    def test_stale_account_is_flagged_and_contributes_nothing(self):
        with mock.patch("sources.x.fetch", return_value=fixture("x_timeline_stale_karpathy.html")):
            res = x.collect(self.config(["karpathy"]), now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["items"], [])
        self.assertEqual(res["notes"]["stale"], ["karpathy"])
        self.assertTrue(res["fetched_ok"])

    def test_spacing_between_accounts(self):
        sleeps = []
        with mock.patch("sources.x.fetch", return_value=fixture("x_timeline_fresh_anthropicai.html")):
            x.collect(self.config(["a", "b", "c"]), now=NOW, hours=24, sleep=sleeps.append)
        self.assertEqual(sleeps, [1.5, 1.5])

    def test_fetch_error_recorded(self):
        with mock.patch("sources.x.fetch", side_effect=FetchError("HTTP 429")):
            res = x.collect(self.config(["a"]), now=NOW, hours=24, sleep=lambda s: None)
        self.assertEqual(res["notes"]["errors"], {"a": "HTTP 429"})
        self.assertFalse(res["fetched_ok"])


class FetchTweet(unittest.TestCase):
    def test_candidate_from_tweet_id(self):
        with mock.patch("sources.x.fetch", return_value=fixture("x_tweet_result.json")):
            c = x.fetch_tweet("2079195918595764300", now=NOW)
        self.assertEqual(c["source"], "x")
        self.assertEqual(c["url"], "https://x.com/RobinhoodApp/status/2079195918595764300")
        self.assertEqual(c["engagement"]["likes"], 8725)
        self.assertTrue(c["title"].startswith("Robinhood is now open to AI agents"))


class Robustness(unittest.TestCase):
    def test_malformed_entry_is_skipped_not_fatal(self):
        good = {"type": "tweet", "content": {"tweet": {"id_str": "1", "conversation_id_str": "1", "full_text": "ok",
                "created_at": "Wed Sep 09 19:02:43 +0000 2026", "favorite_count": 5, "user": {"screen_name": "a"}}}}
        bad = {"type": "tweet", "content": {"tweet": {"id_str": "2", "conversation_id_str": "2", "full_text": "no date", "user": {"screen_name": "a"}}}}
        html = '<script id="__NEXT_DATA__" type="application/json">%s</script>' % json.dumps(
            {"props": {"pageProps": {"timeline": {"entries": [bad, good]}}}})
        rows = x.parse_timeline_html(html)
        self.assertEqual([r["id"] for r in rows], ["1"])

    def test_tweet_result_without_fractional_seconds(self):
        row = x.parse_tweet_json('{"id_str": "9", "created_at": "2026-07-20T12:00:00Z", "favorite_count": 1, "text": "t", "user": {"screen_name": "u"}}')
        self.assertEqual(row["created_at"].isoformat(), "2026-07-20T12:00:00+00:00")

    def test_parse_error_is_recorded_and_next_account_still_runs(self):
        responses = iter(["<html>" + '<script id="__NEXT_DATA__" type="application/json">{broken</script>', fixture("x_timeline_fresh_anthropicai.html")])
        with mock.patch("sources.x.fetch", side_effect=lambda url, **kw: next(responses)):
            res = x.collect({"per_source_cap": 8, "x": {"accounts": ["bad", "AnthropicAI"], "min_likes": 100, "stale_days": 7}},
                            now=NOW, hours=24, sleep=lambda s: None)
        self.assertIn("bad", res["notes"]["errors"])
        self.assertEqual(len(res["items"]), 2)
