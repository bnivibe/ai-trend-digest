import io
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

from sources import common


class RelativeAge(unittest.TestCase):
    def test_short_and_long_forms(self):
        self.assertEqual(common.relative_age_hours("9h ago"), 9.0)
        self.assertEqual(common.relative_age_hours("1d ago"), 24.0)
        self.assertEqual(common.relative_age_hours("Streamed 3 hours ago"), 3.0)
        self.assertEqual(common.relative_age_hours("2 weeks ago"), 336.0)
        self.assertEqual(common.relative_age_hours("3 months ago"), 2160.0)
        self.assertEqual(common.relative_age_hours("6mo"), 4320.0)
        self.assertAlmostEqual(common.relative_age_hours("45 minutes ago"), 0.75)

    def test_unparseable(self):
        self.assertIsNone(common.relative_age_hours(None))
        self.assertIsNone(common.relative_age_hours("Premieres in 2 hours"))
        self.assertIsNone(common.relative_age_hours(""))


class Counts(unittest.TestCase):
    def test_parse_count(self):
        self.assertEqual(common.parse_count("104,604 views"), 104604)
        self.assertEqual(common.parse_count("1.2M views"), 1200000)
        self.assertEqual(common.parse_count("12K"), 12000)
        self.assertEqual(common.parse_count("656"), 656)
        self.assertIsNone(common.parse_count("No views"))
        self.assertIsNone(common.parse_count(None))


class Time(unittest.TestCase):
    def test_parse_iso_accepts_z_and_offset(self):
        a = common.parse_iso("2026-09-08T14:05:57Z")
        b = common.parse_iso("2026-09-09T18:29:00+00:00")
        self.assertEqual(a.tzinfo, timezone.utc)
        self.assertEqual(common.iso(b), "2026-09-09T18:29:00Z")
        self.assertAlmostEqual(common.hours_between(b, a), 28.384, places=2)


class Scores(unittest.TestCase):
    def test_rank_percentile_and_sort(self):
        items = [{"v": 10}, {"v": 30}, {"v": 20}, {"v": None}]
        common.assign_scores(items, lambda it: it["v"])
        self.assertEqual([it["v"] for it in items], [30, 20, 10, None])
        self.assertEqual([it["score"] for it in items], [1.0, 0.75, 0.5, 0.25])

    def test_empty(self):
        self.assertEqual(common.assign_scores([], lambda it: 0), [])


class Candidate(unittest.TestCase):
    def test_shape(self):
        c = common.candidate("hn", 1, "https://e.com", "  Title  ", "a", "2026-09-09T00:00:00Z", 3.14159, {"points": 5}, "x " * 400)
        self.assertEqual(c["id"], "1")
        self.assertEqual(c["title"], "Title")
        self.assertEqual(c["age_hours"], 3.1)
        self.assertEqual(c["engagement"]["points"], 5)
        self.assertIsNone(c["engagement"]["views"])
        self.assertEqual(c["score"], 0.0)
        self.assertLessEqual(len(c["snippet"]), 300)


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {"Retry-After": "1"}, io.BytesIO(b""))


class Fetch(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        ok = mock.MagicMock()
        ok.__enter__.return_value.read.return_value = b"body"
        ok.__enter__.return_value.headers = {}
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[_http_error(429), ok]) as urlopen:
            sleeps = []
            text = common.fetch("http://x", sleep=sleeps.append)
        self.assertEqual(text, "body")
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(sleeps, [2])

    def test_gives_up_with_reason(self):
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[_http_error(503)] * 3):
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://x", sleep=lambda s: None)
        self.assertEqual(str(ctx.exception), "HTTP 503")

    def test_non_retryable_raises_immediately(self):
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[_http_error(404)]) as urlopen:
            with self.assertRaises(common.FetchError):
                common.fetch("http://x", sleep=lambda s: None)
        self.assertEqual(urlopen.call_count, 1)


class CircuitAndBudget(unittest.TestCase):
    def setUp(self):
        common.reset_run(None)

    def tearDown(self):
        common.reset_run(None)

    def test_network_errors_give_up_after_two_attempts(self):
        err = urllib.error.URLError("timed out")
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err] * 5) as urlopen:
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://slow.example/a", sleep=lambda s: None)
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("network:", str(ctx.exception))

    def test_host_is_skipped_after_two_failed_urls(self):
        err = urllib.error.URLError("timed out")
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err] * 10) as urlopen:
            for path in ("a", "b"):
                with self.assertRaises(common.FetchError):
                    common.fetch("http://dead.example/" + path, sleep=lambda s: None)
            calls = urlopen.call_count
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://dead.example/c", sleep=lambda s: None)
        self.assertEqual(urlopen.call_count, calls)  # third URL never hit the network
        self.assertIn("unreachable earlier this run", str(ctx.exception))
        # another host is unaffected
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err] * 2):
            with self.assertRaises(common.FetchError) as ctx2:
                common.fetch("http://alive.example/a", sleep=lambda s: None)
        self.assertIn("network:", str(ctx2.exception))

    def test_deadline_skips_fetch(self):
        common.reset_run(deadline=1.0)  # epoch second 1: long past
        with mock.patch("sources.common.urllib.request.urlopen") as urlopen:
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://x.example/", sleep=lambda s: None)
        urlopen.assert_not_called()
        self.assertIn("time budget exhausted", str(ctx.exception))

    def test_exhausted_429_marks_host_dead(self):
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[_http_error(429)] * 3) as urlopen:
            with self.assertRaises(common.FetchError):
                common.fetch("http://limited.example/a", sleep=lambda s: None)
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://limited.example/b", sleep=lambda s: None)
        self.assertEqual(urlopen.call_count, 3)
        self.assertIn("unreachable earlier this run", str(ctx.exception))

    def test_non_retryable_error_carries_server_message(self):
        err = urllib.error.HTTPError("http://x", 403, "forbidden", {},
                                     io.BytesIO(b'{"message":"This GitHub API path is not available: sessions are bound to their configured repositories."}'))
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err]):
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://x", sleep=lambda s: None)
        self.assertIn("HTTP 403", str(ctx.exception))
        self.assertIn("sessions are bound", str(ctx.exception))

    def test_html_error_body_adds_no_noise(self):
        err = urllib.error.HTTPError("http://x", 404, "nf", {}, io.BytesIO(b"<!DOCTYPE html><html lang=en><title>Error 404</title>"))
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err]):
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://x", sleep=lambda s: None)
        self.assertEqual(str(ctx.exception), "HTTP 404")

    def test_optional_failures_do_not_kill_the_host(self):
        err = urllib.error.URLError("timed out")
        with mock.patch("sources.common.urllib.request.urlopen", side_effect=[err] * 8):
            for path in ("a", "b", "c"):
                with self.assertRaises(common.FetchError):
                    common.fetch("http://mixed.example/" + path, sleep=lambda s: None, optional=True)
            with self.assertRaises(common.FetchError) as ctx:
                common.fetch("http://mixed.example/primary", sleep=lambda s: None)
        self.assertIn("network:", str(ctx.exception))  # still tried, not skipped
