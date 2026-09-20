"""YouTube: the search results page (upload date: today) plus each channel's videos and
Shorts tabs. No login, no API key."""
import json
import re
import time
import urllib.parse
from datetime import timedelta

from .common import (assign_scores, candidate, fetch, hours_between, iso,
                     parse_count, parse_iso, relative_age_hours, result)

# sp=EgIIAg%3D%3D is the "upload date: today" filter; hl/gl pin the English locale so ages read "9h ago".
SEARCH_URL = "https://www.youtube.com/results?search_query={q}&sp=EgIIAg%3D%3D&hl=en&gl=US"
# feeds/videos.xml returned 404 for every channel and every URL form on 2026-09-19, from this
# laptop and from a second network, while the channel pages stayed reachable: the feed endpoint
# is gone, so uploads now come from the channel tabs, which use the newer lockup view models.
CHANNEL_VIDEOS_URL = "https://www.youtube.com/channel/{cid}/videos?hl=en&gl=US"
CHANNEL_SHORTS_URL = "https://www.youtube.com/channel/{cid}/shorts?hl=en&gl=US"
WATCH_URL = "https://www.youtube.com/watch?v={vid}&hl=en"
VIDEO_URL = "https://www.youtube.com/watch?v={vid}"
SHORTS_CHECKED = 2  # newest Shorts per channel whose date is worth a watch-page fetch
_INITIAL = re.compile(r"var ytInitialData = ({.*?});</script>", re.S)
_PLAYER = re.compile(r"var ytInitialPlayerResponse = ({.*?});(?:</script>|var )", re.S)


def _runs(node):
    return "".join(r.get("text", "") for r in (node or {}).get("runs", []))


def _collect(node, key):
    """Every value stored under `key` anywhere in the parsed page."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            if key in o:
                out.append(o[key])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(node)
    return out


def _initial_data(html):
    m = _INITIAL.search(html)
    return json.loads(m.group(1)) if m else None


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


def parse_channel_videos_html(html, channel=""):
    """Uploads from a channel's /videos tab: video_id, title, channel, age_hours, views."""
    data = _initial_data(html)
    if not data:
        return []
    items = []
    for lockup in _collect(data, "lockupViewModel"):
        if lockup.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            continue
        vid = lockup.get("contentId")
        if not vid:
            continue
        md = (lockup.get("metadata") or {}).get("lockupMetadataViewModel", {})
        rows = ((md.get("metadata") or {}).get("contentMetadataViewModel", {}) or {}).get("metadataRows", [])
        parts = [(p.get("text") or {}).get("content") for row in rows for p in row.get("metadataParts", [])]
        parts = [p for p in parts if p]
        items.append({"video_id": vid, "title": (md.get("title") or {}).get("content") or "",
                      "channel": channel,
                      "age_hours": next((relative_age_hours(p) for p in parts if "ago" in p), None),
                      "views": next((parse_count(p) for p in parts if "view" in p), None),
                      "snippet": ""})
    return items


def parse_channel_shorts_html(html, channel=""):
    """Shorts from a channel's /shorts tab, newest first. The tab carries no dates."""
    data = _initial_data(html)
    if not data:
        return []
    items = []
    for short in _collect(data, "shortsLockupViewModel"):
        vid = ((short.get("onTap") or {}).get("innertubeCommand") or {}).get("reelWatchEndpoint", {}).get("videoId")
        if not vid:
            continue
        overlay = short.get("overlayMetadata") or {}
        items.append({"video_id": vid, "title": (overlay.get("primaryText") or {}).get("content") or "",
                      "channel": channel, "age_hours": None,
                      "views": parse_count((overlay.get("secondaryText") or {}).get("content")),
                      "snippet": ""})
    return items


def parse_watch_published(html):
    """The ISO publish date from a watch page, or None."""
    m = _PLAYER.search(html)
    if not m:
        return None
    micro = json.loads(m.group(1)).get("microformat", {}).get("playerMicroformatRenderer", {})
    return micro.get("publishDate")


def recent_shorts(cid, channel, now, hours, sleep, checked=SHORTS_CHECKED):
    """The channel's newest Shorts that fall inside the window. The tab is ordered newest
    first, so the scan stops at the first one that is too old."""
    kept = []
    for short in parse_channel_shorts_html(fetch(CHANNEL_SHORTS_URL.format(cid=cid)), channel)[:checked]:
        published = parse_watch_published(fetch(WATCH_URL.format(vid=short["video_id"])))
        if not published:
            continue
        if hours_between(now, parse_iso(published)) > hours:
            break
        short["published_at"] = published
        kept.append(short)
        sleep(0.5)
    return kept


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


def _collapse(errors, prefix, label, total):
    """One line instead of eleven when every channel fails the same way."""
    same = {k: v for k, v in errors.items() if k.startswith(prefix)}
    if len(same) > 1 and len(set(same.values())) == 1:
        for k in same:
            del errors[k]
        errors[label] = "%s (%d of %d channels)" % (next(iter(same.values())), len(same), total)


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
            raws.extend(parse_channel_videos_html(fetch(CHANNEL_VIDEOS_URL.format(cid=cid)), name))
            fetched_ok = True
        except Exception as e:
            errors["channel:" + name] = str(e) or type(e).__name__
        try:
            raws.extend(recent_shorts(cid, name, now, hours, sleep))
        except Exception as e:
            errors["shorts:" + name] = str(e) or type(e).__name__

    _collapse(errors, "channel:", "channels", len(cfg.get("channels", {})))
    _collapse(errors, "shorts:", "shorts", len(cfg.get("channels", {})))
    by_id = {}
    for raw in raws:  # verified Shorts carry exact timestamps; prefer them over rows without one
        prev = by_id.get(raw["video_id"])
        if prev is None or (raw.get("published_at") and not prev.get("published_at")):
            by_id[raw["video_id"]] = raw
    items = [c for c in (_to_candidate(r, now, hours) for r in by_id.values()) if c]
    assign_scores(items, lambda it: it["engagement"]["views"] / max(it["age_hours"] or 1.0, 1.0))
    return result(items[:cap], fetched_ok, errors=errors, fetched=len(raws))
