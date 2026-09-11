import json
import os
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def resolve(cfg, dotted):
    node = cfg
    for part in dotted.split("."):
        node = node[part]
    return node


class Caps(unittest.TestCase):
    """The owner's rule: keyword lists must not grow without bound. Each list has a cap in
    config.max_per_list; adding beyond it means swapping something out, not appending."""

    def test_every_list_within_its_cap(self):
        cfg = load()
        caps = cfg["max_per_list"]
        self.assertEqual(set(caps), {"youtube.queries", "youtube.channels", "x.accounts", "hn.keywords", "github.keywords", "reddit.subreddits"})
        for dotted, cap in caps.items():
            n = len(resolve(cfg, dotted))
            self.assertLessEqual(n, cap, "%s has %d entries, cap is %d: swap one out instead of adding" % (dotted, n, cap))

    def test_no_duplicates_case_insensitive(self):
        cfg = load()
        for dotted in cfg["max_per_list"]:
            items = resolve(cfg, dotted)
            keys = [str(k).lower() for k in (items.keys() if isinstance(items, dict) else items)]
            self.assertEqual(len(keys), len(set(keys)), "%s has duplicates" % dotted)
