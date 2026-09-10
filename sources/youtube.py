"""YouTube: search results page (upload date: today) and channel RSS feeds. No login, no API key."""
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta

from .common import (assign_scores, candidate, fetch, hours_between, iso,
                     parse_count, parse_iso, relative_age_hours, result)

# sp=EgIIAg%3D%3D is the "upload date: today" filter; hl/gl pin the English locale so ages read "9h ago".
SEARCH_URL = "https://www.youtube.com/results?search_query={q}&sp=EgIIAg%3D%3D&hl=en&gl=US"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
VIDEO_URL = "https://www.youtube.com/watch?v={vid}"
_INITIAL = re.compile(r"var ytInitialData = ({.*?});</script>", re.S)
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}


def _runs(node):
    return "".join(r.get("text", "") for r in (node or {}).get("runs", []))


def parse_search_html(html):
    """Raw video dicts from a results page: video_id, title, channel, age_hours, views, snippet."""
    m = _INITIAL.search(html)
    if not m:
        return []
    found = []

    def walk(o):
        if isinstance(o, dict):
            if "videoRenderer" in o:
                found.append(o["videoRenderer"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    items = []
    for v in found:
        vid = v.get("videoId")
        if not vid:
            continue
        snippet = " ".join(_runs(s.get("snippetText")) for s in v.get("detailedMetadataSnippets", []))
        items.append({"video_id": vid, "title": _runs(v.get("title")), "channel": _runs(v.get("ownerText")),
                      "age_hours": relative_age_hours((v.get("publishedTimeText") or {}).get("simpleText")),
                      "views": parse_count((v.get("viewCountText") or {}).get("simpleText")),
                      "snippet": snippet})
    return items


def parse_rss_xml(xml_text):
    """Raw video dicts from a channel feed: video_id, title, channel, published_at (ISO), views, snippet."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    channel = root.findtext("a:title", default="", namespaces=NS)
    items = []
    for e in root.findall("a:entry", NS):
        stats = e.find("media:group/media:community/media:statistics", NS)
        items.append({"video_id": e.findtext("yt:videoId", default="", namespaces=NS),
                      "title": e.findtext("a:title", default="", namespaces=NS),
                      "channel": channel,
                      "published_at": e.findtext("a:published", default="", namespaces=NS),
                      "views": int(stats.get("views")) if stats is not None and stats.get("views") else None,
                      "snippet": e.findtext("media:group/media:description", default="", namespaces=NS)})
    return items


def _to_candidate(raw, now, hours):
    """A candidate when the video is inside the window, else None."""
    if raw.get("published_at"):
        published = parse_iso(raw["published_at"])
        age = hours_between(now, published)
        published_iso = iso(published)
    else:
        age = raw.get("age_hours")
        published_iso = iso(now - timedelta(hours=age)) if age is not None else None
    if age is None or age > hours:
        return None
    return candidate("youtube", raw["video_id"], VIDEO_URL.format(vid=raw["video_id"]), raw["title"],
                     raw["channel"], published_iso, age, {"views": raw.get("views") or 0}, raw.get("snippet", ""))


def collect(config, now, hours, sleep=time.sleep):
    cfg = config["youtube"]
    cap = config.get("per_source_cap", 8)
    raws, fetched_ok, errors = [], False, {}
    for q in cfg.get("queries", []):
        try:
            raws.extend(parse_search_html(fetch(SEARCH_URL.format(q=urllib.parse.quote_plus(q)))))
            fetched_ok = True
        except Exception as e:  # FetchError, JSON errors, anything: record and continue with the next query
            errors["search:" + q] = str(e) or type(e).__name__
        sleep(1)
    for name, cid in cfg.get("channels", {}).items():
        try:
            raws.extend(parse_rss_xml(fetch(RSS_URL.format(cid=cid))))
            fetched_ok = True
        except Exception as e:
            errors["rss:" + name] = str(e) or type(e).__name__
    rss_errors = {k: v for k, v in errors.items() if k.startswith("rss:")}
    if len(rss_errors) > 1 and len(set(rss_errors.values())) == 1:
        # every channel feed failed the same way (the cloud sandbox gets HTTP 404 from YouTube):
        # one line keeps the daily footer readable
        for k in rss_errors:
            del errors[k]
        errors["rss"] = "%s (%d of %d channels)" % (next(iter(rss_errors.values())), len(rss_errors), len(cfg.get("channels", {})))
    by_id = {}
    for raw in raws:  # RSS rows carry exact timestamps; prefer them over search rows for the same video
        prev = by_id.get(raw["video_id"])
        if prev is None or (raw.get("published_at") and not prev.get("published_at")):
            by_id[raw["video_id"]] = raw
    items = [c for c in (_to_candidate(r, now, hours) for r in by_id.values()) if c]
    assign_scores(items, lambda it: it["engagement"]["views"] / max(it["age_hours"] or 1.0, 1.0))
    return result(items[:cap], fetched_ok, errors=errors, fetched=len(raws))
