import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import post_discord


def digest(n_topics=5, summary="한국어 두 줄 요약입니다. 개발자에게 중요한 이유입니다."):
    return {
        "date_local": "2026-09-09", "weekday_ko": "수", "one_liner": "오늘의 흐름 한 문장.",
        "topics": [{"title": "Topic %d" % i, "summary": summary, "days_on_top": 2 if i == 1 else 1,
                    "sources": [{"source": "youtube", "label": "IBM Technology", "metric": "12,041 views", "age": "9h", "url": "https://www.youtube.com/watch?v=6AuYLbHqirk"},
                                {"source": "x", "label": "@AnthropicAI", "metric": "10,015 likes", "age": "10h", "url": "https://x.com/AnthropicAI/status/1"},
                                {"source": "hn", "label": "HN", "metric": "672 points", "age": "16h", "url": "https://news.ycombinator.com/item?id=49610538"}]}
                   for i in range(1, n_topics + 1)],
        "stats": {"candidates": 41, "sources_total": 5, "sources_ok": 4, "sources_failed": {"reddit": "HTTP 429"}, "parser_suspect": []},
    }


class Validate(unittest.TestCase):
    def test_good_digest(self):
        self.assertEqual(post_discord.validate(digest()), [])

    def test_catches_problems(self):
        d = digest(2)
        d["topics"][0]["summary"] = "Bad — em dash"
        d["topics"][1]["sources"][0]["url"] = "no-scheme"
        problems = post_discord.validate(d)
        self.assertTrue(any("topics must be 3 to 5" in p for p in problems))
        self.assertTrue(any("em dash" in p for p in problems))
        self.assertTrue(any("source without url" in p for p in problems))


class Render(unittest.TestCase):
    def test_shape(self):
        p = post_discord.render(digest(), prefix="[TEST]")
        self.assertEqual(p["username"], "AI Trend")
        self.assertTrue(p["content"].startswith("[TEST] 📡 AI 트렌드 · 2026-09-09 (수)\n오늘 한 줄: "))
        self.assertEqual(len(p["embeds"]), 5)
        self.assertEqual(p["embeds"][0]["title"], "1. Topic 1 · 2일째 상위")
        self.assertEqual(p["embeds"][1]["title"], "2. Topic 2")
        self.assertIn("▸ YouTube · [IBM Technology](https://www.youtube.com/watch?v=6AuYLbHqirk) · 12,041 views · 9h", p["embeds"][0]["description"])
        self.assertEqual(p["embeds"][-1]["footer"]["text"], "후보 41건 · 소스 5개 중 4개 성공 (Reddit: HTTP 429)")
        self.assertEqual(p["allowed_mentions"], {"parse": []})
        self.assertNotIn("footer", p["embeds"][0])

    def test_budget(self):
        p = post_discord.render(digest(summary="가나다라마바사. " * 300))
        self.assertLessEqual(post_discord.total_chars(p), 6000)
        self.assertTrue(all(len(e["description"]) <= 4096 for e in p["embeds"]))
        self.assertTrue(all("[" in e["description"] for e in p["embeds"]))


class Post(unittest.TestCase):
    def test_retries_then_raises_with_body(self):
        err = urllib.error.HTTPError("http://w", 400, "bad", {}, io.BytesIO(b'{"embeds": ["Must be 4096 or fewer"]}'))
        with mock.patch("post_discord.urllib.request.urlopen", side_effect=err):
            with self.assertRaises(SystemExit) as ctx:
                post_discord.post({"content": "x", "embeds": []}, "http://w", sleep=lambda s: None)
        self.assertIn("HTTP 400", str(ctx.exception))
        self.assertIn("4096", str(ctx.exception))

    def test_wait_param_added(self):
        ok = mock.MagicMock()
        ok.__enter__.return_value.status = 200
        with mock.patch("post_discord.urllib.request.urlopen", return_value=ok) as urlopen:
            post_discord.post({"content": "x", "embeds": []}, "https://discord.com/api/webhooks/1/abc")
        self.assertTrue(urlopen.call_args[0][0].full_url.endswith("?wait=true"))


class Main(unittest.TestCase):
    def write(self, d):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(d, self.tmp)
        self.tmp.close()
        return self.tmp.name

    def tearDown(self):
        if getattr(self, "tmp", None):
            os.unlink(self.tmp.name)

    def test_validate_flag(self):
        self.assertEqual(post_discord.main(["--validate", self.write(digest())]), 0)
        self.assertEqual(post_discord.main(["--validate", self.write(digest(1))]), 1)

    def test_missing_webhook_skips(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("post_discord.post") as p:
            rc = post_discord.main([self.write(digest())])
        self.assertEqual(rc, 0)
        p.assert_not_called()

    def test_failure_notice_dry_run(self):
        with mock.patch("builtins.print") as pr:
            rc = post_discord.main(["--failure", "only 3 candidates", "--dry-run", "--prefix", "[TEST]"])
        self.assertEqual(rc, 0)
        printed = pr.call_args[0][0]
        self.assertIn("오늘은 수집 실패. only 3 candidates", printed)
        self.assertIn("[TEST] ⚠️ AI 트렌드", printed)


class Budget(unittest.TestCase):
    def test_total_chars_counts_embeds_only(self):
        p = {"content": "x" * 1000, "embeds": [{"title": "ab", "description": "cde", "footer": {"text": "f"}}]}
        self.assertEqual(post_discord.total_chars(p), 6)

    def test_one_liner_length_checked(self):
        d = digest()
        d["one_liner"] = "가" * 121
        self.assertTrue(any("one_liner over 120" in p for p in post_discord.validate(d)))
