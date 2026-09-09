#!/usr/bin/env python3
"""Collect AI trend candidates from all sources into out/candidates.json.

  python3 collect.py                      # --hours from config, writes out/candidates.json
  python3 collect.py --dry-run            # print the top candidates per source, write nothing
  python3 collect.py --probe              # one GET per host, print reachability, exit 1 if discord.com is blocked
  python3 collect.py --only youtube,hn    # subset of sources
  python3 collect.py --budget 240         # seconds; fetches past the deadline are skipped (default from config)

Sources run in parallel threads (one per source; calls inside a source stay sequential and spaced).
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from sources import common, github, hn, reddit, x, youtube
from sources.common import FetchError, fetch, iso, now_utc

SOURCES = {"youtube": youtube, "x": x, "hn": hn, "github": github, "reddit": reddit}
PROBE = {
    "youtube.com": "https://www.youtube.com/feeds/videos.xml?channel_id=UCrDwWp7EBBv4NwvScIpBDOA",
    "syndication.twitter.com": "https://syndication.twitter.com/srv/timeline-profile/screen-name/OpenAIDevs",
    "cdn.syndication.twimg.com": "https://cdn.syndication.twimg.com/tweet-result?id=20&token=a",
    "hn.algolia.com": "https://hn.algolia.com/api/v1/search?query=AI&hitsPerPage=1",
    "github.com": "https://github.com/trending?since=daily",
    "reddit.com": "https://www.reddit.com/r/ClaudeAI/hot.rss?limit=1",
    "discord.com": "https://discord.com/api/v10/gateway",
}


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def verdict(meta, config):
    min_c, min_s = config.get("min_candidates", 8), config.get("min_sources_ok", 2)
    if meta["candidates"] < min_c:
        return "insufficient: only %d candidates (min %d)" % (meta["candidates"], min_c)
    if meta["sources_ok"] < min_s:
        return "insufficient: only %d sources ok (min %d)" % (meta["sources_ok"], min_s)
    return "ok"


def _run_one(mod, config, now, hours):
    """One source, fully isolated: returns (meta entry, items). Never raises."""
    t0 = time.time()
    try:
        res = mod.collect(config, now=now, hours=hours)
        items = res["items"]
        if items:
            status = "ok"
        elif res.get("fetched_ok"):
            status = "parser_suspect"  # HTTP succeeded but nothing parsed: the page structure may have changed
        else:
            status = "failed"
        entry = {"status": status, "count": len(items), "seconds": round(time.time() - t0, 1)}
        entry.update(res.get("notes", {}))
        return entry, items
    except Exception as e:
        return {"status": "failed", "count": 0, "seconds": round(time.time() - t0, 1),
                "error": "%s: %s" % (type(e).__name__, e)}, []


def run(config, hours, only=None, now=None, sources=None, budget=None):
    """Run every source in parallel and in isolation; one failure never aborts the run.
    budget: seconds for the whole collection; fetches attempted after the deadline are skipped."""
    now = now or now_utc()
    sources = sources if sources is not None else SOURCES
    selected = [(n, m) for n, m in sources.items() if not only or n in only]
    common.reset_run(time.time() + budget if budget else None)
    meta = {"run_at": iso(now), "hours": hours, "budget_seconds": budget, "sources": {}}
    candidates = []
    with ThreadPoolExecutor(max_workers=max(1, len(selected))) as pool:
        futures = [(name, pool.submit(_run_one, mod, config, now, hours)) for name, mod in selected]
        for name, fut in futures:
            entry, items = fut.result()
            meta["sources"][name] = entry
            candidates.extend(items)
    meta["candidates"] = len(candidates)
    meta["sources_total"] = len(meta["sources"])
    meta["sources_ok"] = sum(1 for s in meta["sources"].values() if s["status"] == "ok")
    meta["sources_failed"] = {n: (s.get("error") or s["status"]) for n, s in meta["sources"].items() if s["status"] != "ok"}
    meta["verdict"] = verdict(meta, config)
    return {"meta": meta, "candidates": candidates}


def probe():
    blocked = []
    for host, url in PROBE.items():
        try:
            fetch(url, timeout=15, retries=1)
            print("ok      %s" % host)
        except FetchError as e:
            print("BLOCKED %s (%s)" % (host, e))
            blocked.append(host)
    return 1 if "discord.com" in blocked else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    p.add_argument("--hours", type=float)
    p.add_argument("--out", default="out/candidates.json")
    p.add_argument("--only")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--budget", type=float, help="seconds for the whole collection (default: config budget_seconds, 240)")
    a = p.parse_args(argv)
    if a.probe:
        return probe()
    config = load_config(a.config)
    hours = a.hours or config.get("hours", 24)
    budget = a.budget or config.get("budget_seconds", 240)
    t0 = time.time()
    data = run(config, hours, only=a.only.split(",") if a.only else None, budget=budget)
    data["meta"]["elapsed_seconds"] = round(time.time() - t0, 1)
    if a.dry_run:
        for name, info in data["meta"]["sources"].items():
            print("== %s: %s" % (name, json.dumps(info, ensure_ascii=False)))
            for c in [c for c in data["candidates"] if c["source"] == name][:5]:
                print("   %.2f %s | %s | %s" % (c["score"], c["title"][:70], c["author"], c["url"]))
        print("verdict: %s (%.1fs)" % (data["meta"]["verdict"], data["meta"]["elapsed_seconds"]))
        return 0
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    m = data["meta"]
    print("wrote %s: %d candidates, %d/%d sources ok, %.1fs, verdict=%s" % (a.out, m["candidates"], m["sources_ok"], m["sources_total"], m["elapsed_seconds"], m["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
