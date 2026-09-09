"""Reddit hot listings via RSS. The JSON endpoint is 403 without OAuth and RSS carries no scores,
so the hot rank is the metric. Posts older than three windows (72 h by default) are dropped: they are pinned."""
import re
import time
import xml.etree.ElementTree as ET

from .common import FetchError, assign_scores, candidate, fetch, hours_between, iso, parse_iso, result

RSS_URL = "https://www.reddit.com/r/{sub}/hot.rss?limit=10"
NS = {"a": "http://www.w3.org/2005/Atom"}


def parse_rss_xml(xml_text):
    root = ET.fromstring(xml_text.encode("utf-8"))
    rows = []
    for rank, e in enumerate(root.findall("a:entry", NS), start=1):
        link = e.find("a:link", NS)
        content = e.findtext("a:content", default="", namespaces=NS)
        rows.append({"id": e.findtext("a:id", default="", namespaces=NS), "rank": rank,
                     "title": e.findtext("a:title", default="", namespaces=NS),
                     "url": link.get("href") if link is not None else "",
                     "author": e.findtext("a:author/a:name", default="", namespaces=NS),
                     "published_at": e.findtext("a:published", default="", namespaces=NS),
                     "snippet": re.sub(r"<[^>]+>", " ", content)})
    return rows


def collect(config, now, hours, sleep=time.sleep):
    cfg = config["reddit"]
    cap = config.get("per_source_cap", 8)
    top_n = cfg.get("top_n", 5)
    items, errors, fetched_ok = [], {}, False
    for i, sub in enumerate(cfg.get("subreddits", [])):
        if i:
            sleep(cfg.get("spacing_seconds", 3))
        try:
            rows = parse_rss_xml(fetch(RSS_URL.format(sub=sub)))
            fetched_ok = True
        except (FetchError, ET.ParseError) as e:
            errors[sub] = str(e)
            continue
        for r in rows[:top_n]:
            published = parse_iso(r["published_at"]) if r["published_at"] else None
            age = hours_between(now, published) if published else None
            if age is not None and age > hours * 3:
                continue
            items.append(candidate("reddit", r["id"], r["url"], r["title"], "r/%s %s" % (sub, r["author"]),
                                   iso(published) if published else None, age, {"rank": r["rank"]}, r["snippet"]))
    assign_scores(items, lambda it: -it["engagement"]["rank"])
    return result(items[:cap], fetched_ok, errors=errors)
