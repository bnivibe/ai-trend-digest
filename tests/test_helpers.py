import unittest

from tests.helpers import fixture


class FixtureHelper(unittest.TestCase):
    def test_loads_gzipped_text(self):
        html = fixture("youtube_search_today_en.html")
        self.assertIn("ytInitialData", html)
        self.assertGreater(len(html), 100000)

    def test_missing_fixture_raises(self):
        with self.assertRaises(FileNotFoundError):
            fixture("does_not_exist.txt")
