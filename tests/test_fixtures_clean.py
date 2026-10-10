import importlib.util
import os
import re
import unittest

from tests.helpers import HERE, fixture

FIXTURES = os.path.join(HERE, "fixtures")
_spec = importlib.util.spec_from_file_location("minimize", os.path.join(FIXTURES, "minimize.py"))
minimize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minimize)

# What a raw capture carries about whoever requested it. None of it may reach a committed fixture.
LEAKS = {
    "remoteHost": re.compile(r"remoteHost"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "visitorData value": re.compile(r'"visitorData"\s*:\s*"(?!REDACTED")'),
    "ytcfg visitor fields": re.compile(r"VISITOR_DATA|DATASYNC_ID|ytcfg\.set"),
    "GitHub visitor payload": re.compile(r"visitor-payload|octolytics"),
    "requester ip param": re.compile(r'(?:[?&]|\\u0026)ip=(?!0\.0\.0\.0(?:[&\\"\s]|$))'),
}


class FixturesAreClean(unittest.TestCase):
    def test_no_requester_data_in_any_fixture(self):
        for name in sorted(os.listdir(FIXTURES)):
            if not name.endswith(".gz"):
                continue
            text = fixture(name[:-3])
            for what, pattern in LEAKS.items():
                self.assertIsNone(pattern.search(text), "%s in %s: run it through minimize.py" % (what, name))


class Minimize(unittest.TestCase):
    PAGE = ('<html><script>ytcfg.set({"VISITOR_DATA": "abc", "remoteHost": "203.0.113.7"})</script>'
            '<script nonce="n">var ytInitialData = {"responseContext": {"visitorData": "Cgt4eXo%3D"}, '
            '"url": "https://r1.example/videoplayback?expire=1\\u0026ip=2001:db8::1\\u0026id=9", '
            '"other": "https://r1.example/x?ip=203.0.113.7&id=9"};</script><p>footer</p></html>')

    def test_youtube_keeps_only_initial_data_and_redacts_the_requester(self):
        out = minimize.youtube(self.PAGE)
        self.assertTrue(out.startswith("<script>var ytInitialData = {"))
        self.assertNotIn("ytcfg", out)
        self.assertNotIn("footer", out)
        self.assertNotIn("203.0.113.7", out)
        self.assertNotIn("2001:db8", out)
        self.assertIn("\\u0026ip=0.0.0.0\\u0026id=9", out)
        self.assertIn("?ip=0.0.0.0&id=9", out)
        self.assertIn('"visitorData": "REDACTED"', out)
        self.assertEqual(minimize.youtube(out), out, "running it twice changes nothing")

    def test_refuses_a_page_without_the_parsed_block(self):
        for kind in ("youtube", "x", "github"):
            with self.assertRaises(ValueError):
                minimize.KINDS[kind]("<html>blocked</html>")
