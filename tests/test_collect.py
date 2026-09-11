import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

import collect
from sources.common import candidate, result

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
CONFIG = {"hours": 24, "per_source_cap": 8, "min_candidates": 8, "min_sources_ok": 2}


def _items(n, source):
    return [candidate(source, i, "https://e.com/%d" % i, "t%d" % i, "a", None, 1.0, {"points": i}) for i in range(n)]


def fake_sources():
    good = SimpleNamespace(collect=lambda config, now, hours: result(_items(3, "good"), True, errors={}))
    empty = SimpleNamespace(collect=lambda config, now, hours: result([], True))
    down = SimpleNamespace(collect=lambda config, now, hours: result([], False, errors={"x": "HTTP 503"}))

    def boom(config, now, hours):
        raise KeyError("config missing")

    return {"good": good, "empty": empty, "down": down, "boom": SimpleNamespace(collect=boom)}


class Run(unittest.TestCase):
    def test_isolation_statuses_and_verdict(self):
        data = collect.run(CONFIG, 24, now=NOW, sources=fake_sources())
        s = data["meta"]["sources"]
        self.assertEqual(s["good"]["status"], "ok")
        self.assertEqual(s["empty"]["status"], "parser_suspect")
        self.assertEqual(s["down"]["status"], "failed")
        self.assertEqual(s["boom"]["status"], "failed")
        self.assertIn("KeyError", s["boom"]["error"])
        self.assertEqual(data["meta"]["candidates"], 3)
        self.assertEqual(data["meta"]["sources_ok"], 1)
        self.assertEqual(data["meta"]["sources_total"], 4)
        self.assertEqual(set(data["meta"]["sources_failed"]), {"empty", "down", "boom"})
        self.assertTrue(data["meta"]["verdict"].startswith("insufficient: only 3 candidates"))
        self.assertEqual(data["meta"]["run_at"], "2026-09-09T06:00:00Z")

    def test_only_filters_sources(self):
        data = collect.run(CONFIG, 24, only=["good"], now=NOW, sources=fake_sources())
        self.assertEqual(list(data["meta"]["sources"]), ["good"])

    def test_verdict_ok(self):
        srcs = {"a": SimpleNamespace(collect=lambda c, now, hours: result(_items(5, "a"), True)),
                "b": SimpleNamespace(collect=lambda c, now, hours: result(_items(5, "b"), True))}
        data = collect.run(CONFIG, 24, now=NOW, sources=srcs)
        self.assertEqual(data["meta"]["verdict"], "ok")


class Main(unittest.TestCase):
    def test_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w") as f:
                json.dump(CONFIG, f)
            out = os.path.join(d, "out", "candidates.json")
            with mock.patch.dict(collect.SOURCES, fake_sources(), clear=True):
                rc = collect.main(["--config", cfg, "--out", out])
            self.assertEqual(rc, 0)
            with open(out) as f:
                data = json.load(f)
            self.assertEqual(len(data["candidates"]), 3)
            self.assertIn("verdict", data["meta"])


class Parallel(unittest.TestCase):
    def test_sources_run_concurrently_and_keep_order(self):
        import time as _t

        def slow(config, now, hours):
            _t.sleep(0.3)
            return result(_items(2, "s"), True)

        srcs = {"a": SimpleNamespace(collect=slow), "b": SimpleNamespace(collect=slow),
                "c": SimpleNamespace(collect=slow), "d": SimpleNamespace(collect=slow)}
        t0 = _t.time()
        data = collect.run(CONFIG, 24, now=NOW, sources=srcs, budget=60)
        self.assertLess(_t.time() - t0, 0.9)
        self.assertEqual(list(data["meta"]["sources"]), ["a", "b", "c", "d"])
        self.assertEqual(data["meta"]["candidates"], 8)
        self.assertEqual(data["meta"]["budget_seconds"], 60)


class Skip(unittest.TestCase):
    def test_skipped_sources_are_left_out_and_recorded(self):
        srcs = fake_sources()
        data = collect.run(CONFIG, 24, now=NOW, sources=srcs, skip=["boom", "down"])
        self.assertEqual(list(data["meta"]["sources"]), ["good", "empty"])
        self.assertEqual(data["meta"]["skipped"], ["boom", "down"])
        self.assertEqual(data["meta"]["sources_total"], 2)
