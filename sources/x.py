"""X: per-account timelines via the public syndication widget endpoint. No login.

Known limit (verified 2026-09-09): the endpoint serves a stale cached timeline for some accounts
(karpathy, simonw, swyx ended in Oct/Nov 2025) while org accounts (AnthropicAI, OpenAIDevs) are current.
Stale accounts are reported in notes['stale'] and contribute nothing.
"""
import html as htmllib
import json
import re
import sys
import time
from datetime import datetime, timezone

from .common import assign_scores, candidate, fetch, hours_between, iso, now_utc, parse_iso, result

TIMELINE_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
TWEET_URL = "https://cdn.syndication.twimg.com/tweet-result?id={id}&token=a"
STATUS_URL = "https://x.com/{handle}/status/{id}"
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_CREATED = "%a %b %d %H:%M:%S %z %Y"


def parse_timeline_html(html):
    """Original tweets only (no retweets, no replies or thread continuations)."""
    m = _NEXT.search(html)
    if not m:
        return []
    data = json.loads(m.group(1))
    entries = data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
    rows = []
    for e in entries:
        if e.get("type") != "tweet":
            continue
        t = e.get("content", {}).get("tweet", {})
        text = htmllib.unescape(t.get("full_text") or t.get("text") or "")
        if text.startswith("RT @"):
            continue
        if t.get("conversation_id_str") and t.get("conversation_id_str") != t.get("id_str"):
            continue
        try:
            created = datetime.strptime(t["created_at"], _CREATED).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue  # one malformed entry must not kill the whole timeline
        rows.append({"id": t.get("id_str"), "handle": (t.get("user") or {}).get("screen_name", ""),
                     "text": text, "created_at": created,
                     "likes": t.get("favorite_count") or 0, "retweets": t.get("retweet_count") or 0})
    return rows


class TweetUnavailable(Exception):
    """tweet-result held no tweet, e.g. a TweetTombstone for a deleted post (seen 2026-10-30)."""


def parse_tweet_json(text):
    """tweet-result JSON -> the same row shape as parse_timeline_html."""
    t = json.loads(text)
    if t.get("__typename") == "TweetWithVisibilityResults":
        t = t.get("tweet") or {}
    if "created_at" not in t:
        reason = ((t.get("tombstone") or {}).get("text") or {}).get("text")
        raise TweetUnavailable("%s: %s" % (t["__typename"], reason) if reason else "no tweet in the response")
    created = parse_iso(t["created_at"])  # accepts both '...:11.000Z' and '...:11Z'
    return {"id": t.get("id_str"), "handle": (t.get("user") or {}).get("screen_name", ""),
            "text": t.get("text", ""), "created_at": created,
            "likes": t.get("favorite_count") or 0, "retweets": 0}


def _to_candidate(row, now):
    age = hours_between(now, row["created_at"])
    title = row["text"].split("\n")[0][:120]
    return candidate("x", row["id"], STATUS_URL.format(handle=row["handle"], id=row["id"]), title,
                     "@" + row["handle"], iso(row["created_at"]), age, {"likes": row["likes"]}, row["text"])


def collect(config, now, hours, sleep=time.sleep):
    cfg = config["x"]
    cap = config.get("per_source_cap", 8)
    stale_hours = cfg.get("stale_days", 7) * 24
    items, stale, errors, fetched_ok = [], [], {}, False
    for i, handle in enumerate(cfg.get("accounts", [])):
        if i:
            sleep(cfg.get("spacing_seconds", 1.5))
        try:
            rows = parse_timeline_html(fetch(TIMELINE_URL.format(handle=handle)))
            fetched_ok = True
        except Exception as e:  # FetchError, JSON errors, anything: record and move to the next account
            errors[handle] = str(e) or type(e).__name__
            continue
        if rows and hours_between(now, max(r["created_at"] for r in rows)) > stale_hours:
            stale.append(handle)
        for r in rows:
            if hours_between(now, r["created_at"]) <= hours and r["likes"] >= cfg.get("min_likes", 0):
                items.append(_to_candidate(r, now))
    assign_scores(items, lambda it: it["engagement"]["likes"])
    return result(items[:cap], fetched_ok, errors=errors, stale=stale)


def fetch_tweet(tweet_id, now=None):
    """One tweet by id as a candidate. Used by the enrichment step described in prompt/digest.md."""
    return _to_candidate(parse_tweet_json(fetch(TWEET_URL.format(id=tweet_id))), now or now_utc())


def main(argv):
    if len(argv) != 3 or argv[1] != "tweet":
        print("usage: python3 -m sources.x tweet <tweet_id>")
        return 2
    try:
        print(json.dumps(fetch_tweet(argv[2]), ensure_ascii=False, indent=2))
    except TweetUnavailable as e:
        sys.stderr.write("tweet %s unavailable: %s\n" % (argv[2], e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
