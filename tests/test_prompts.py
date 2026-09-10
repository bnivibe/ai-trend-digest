import os
import re
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(HERE, "prompt", name), encoding="utf-8") as f:
        return f.read()


class Taste(unittest.TestCase):
    def test_entries_are_numbered_dated_and_capped(self):
        body = read("taste.md").split("## Entries", 1)[1]
        entries = re.findall(r"^\d+\. (\d{4}-\d\d-\d\d) · ", body, re.M)
        self.assertTrue(1 <= len(entries) <= 20, "taste.md holds 1 to 20 entries")
        self.assertEqual(entries, sorted(entries), "newest entry last")
        self.assertEqual(len(re.findall(r"^\s+Why: ", body, re.M)), len(entries), "every entry has a Why line")

    def test_digest_prompt_reads_taste(self):
        self.assertIn("prompt/taste.md", read("digest.md"))

    def test_no_em_dashes_in_prompts(self):
        for name in ("digest.md", "routine.md", "taste.md"):
            self.assertNotIn("—", read(name), name)
