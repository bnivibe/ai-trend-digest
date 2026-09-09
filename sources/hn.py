"""Hacker News via the Algolia search API. No auth."""
import json
import time
import urllib.parse

from .common import FetchError, assign_scores, candidate, fetch, hours_between, iso, parse_iso, result

API = ("https://hn.algolia.com/api/v1/search?query={q}&tags=story"
       "&numericFilters=created_at_i%3E{since},points%3E{minp}&hitsPerPage=20")
ITEM_URL = "https://news.ycombinator.com/item?id={id}"


def parse_hits(json_text):
    hits = json.loads(json_text).get("hits", [])
    return [{"id": str(h["objectID"]), "title": h.get("title") or "",
             "url": h.get("url") or ITEM_URL.format(id=h["objectID"]),
             "points": h.get("points") or 0, "comments": h.get("num_comments") or 0,
             "created_at": h.get("created_at"), "author": h.get("author") or ""} for h in hits]


def collect(config, now, hours, sleep=time.sleep):
    cfg = config["hn"]
    cap = config.get("per_source_cap", 8)
    since = int(now.timestamp()) - int(hours * 3600)
    by_id, errors, fetched_ok = {}, {}, False
    for i, kw in enumerate(cfg.get("keywords", [])):
        if i:
            sleep(0.5)
        url = API.format(q=urllib.parse.quote_plus(kw), since=since, minp=cfg.get("min_points", 50))
        try:
            for h in parse_hits(fetch(url)):
                by_id[h["id"]] = h
            fetched_ok = True
        except (FetchError, ValueError) as e:
            errors[kw] = str(e)
    items = []
    for h in by_id.values():
        created = parse_iso(h["created_at"])
        age = hours_between(now, created)
        if age > hours:
            continue
        snippet = "%d points, %d comments. HN: %s" % (h["points"], h["comments"], ITEM_URL.format(id=h["id"]))
        items.append(candidate("hn", h["id"], h["url"], h["title"], h["author"], iso(created), age,
                               {"points": h["points"]}, snippet))
    assign_scores(items, lambda it: it["engagement"]["points"])
    return result(items[:cap], fetched_ok, errors=errors)
