#!/usr/bin/env python3
"""Post the digest (or a failure notice) to Discord through a webhook.

  python3 post_discord.py out/digest.json              # post the digest
  python3 post_discord.py out/digest.json --dry-run    # print the payload, send nothing
  python3 post_discord.py out/digest.json --prefix "[TEST]"
  python3 post_discord.py --validate out/digest.json   # schema check only, exit 1 on problems
  python3 post_discord.py --failure "reason"           # post the failure notice

Env: AI_TREND_DISCORD_WEBHOOK. When unset: prints 'send skipped: no webhook' and exits 0.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from sources.common import UA

ENV = "AI_TREND_DISCORD_WEBHOOK"
COLORS = [0x5865F2, 0x57F287, 0xFEE75C, 0xEB459E, 0x99AAB5]
LABEL = {"youtube": "YouTube", "x": "X", "hn": "HN", "github": "GitHub", "reddit": "Reddit", "web": "Web"}
WEEKDAY_KO = "월화수목금토일"
MESSAGE_LIMIT = 6000
EMBED_LIMIT = 4096
EM_DASH = "—"


def local_date():
    """(YYYY-MM-DD, weekday letter) in America/Vancouver; UTC if tz data is missing."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Vancouver"))
    except Exception:
        now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d"), WEEKDAY_KO[now.weekday()]


def validate(digest):
    """Problems with the digest; an empty list means it is usable."""
    problems = []
    for key in ("date_local", "one_liner", "topics", "stats"):
        if key not in digest:
            problems.append("missing key: %s" % key)
    topics = digest.get("topics") or []
    if not 3 <= len(topics) <= 5:
        problems.append("topics must be 3 to 5, got %d" % len(topics))
    for i, t in enumerate(topics, start=1):
        for key in ("title", "summary", "sources"):
            if not t.get(key):
                problems.append("topic %d: missing %s" % (i, key))
        if len(t.get("summary") or "") > 400:
            problems.append("topic %d: summary over 400 chars" % i)
        if EM_DASH in (t.get("summary") or "") + (t.get("title") or ""):
            problems.append("topic %d: em dash" % i)
        for s in t.get("sources") or []:
            if not str(s.get("url") or "").startswith("http"):
                problems.append("topic %d: source without url" % i)
    if EM_DASH in str(digest.get("one_liner") or ""):
        problems.append("one_liner: em dash")
    return problems


def render(digest, prefix=""):
    header = "📡 AI 트렌드 · %s (%s)" % (digest["date_local"], digest.get("weekday_ko", ""))
    if prefix:
        header = prefix + " " + header
    content = header + "\n오늘 한 줄: " + digest["one_liner"].strip()
    embeds = []
    for i, t in enumerate(digest["topics"][:5]):
        title = "%d. %s" % (i + 1, t["title"].strip())
        if int(t.get("days_on_top") or 1) > 1:
            title += " · %d일째 상위" % int(t["days_on_top"])
        lines = []
        for s in (t.get("sources") or [])[:3]:
            parts = [LABEL.get(s.get("source"), s.get("source") or "Web"), "[%s](%s)" % (s.get("label") or "link", s["url"])]
            parts += [v for v in (s.get("metric"), s.get("age")) if v]
            lines.append("▸ " + " · ".join(parts))
        embeds.append({"title": title[:256], "description": t["summary"].strip() + "\n\n" + "\n".join(lines),
                       "color": COLORS[i % len(COLORS)]})
    st = digest.get("stats") or {}
    footer = "후보 %s건 · 소스 %s개 중 %s개 성공" % (st.get("candidates", "?"), st.get("sources_total", "?"), st.get("sources_ok", "?"))
    failed = st.get("sources_failed") or {}
    if failed:
        footer += " (" + ", ".join("%s: %s" % (LABEL.get(k, k), v) for k, v in failed.items()) + ")"
    if embeds:
        embeds[-1]["footer"] = {"text": footer[:2048]}
    return enforce_budget({"username": "AI Trend", "content": content[:2000], "embeds": embeds,
                           "allowed_mentions": {"parse": []}})


def total_chars(payload):
    return len(payload["content"]) + sum(len(e.get("title", "")) + len(e.get("description", "")) +
                                         len((e.get("footer") or {}).get("text", "")) for e in payload["embeds"])


def enforce_budget(payload):
    """Every embed under 4,096 chars, the message under 6,000. Cuts: drop source lines from the
    lowest-ranked topics first (never the last line of a topic), then shorten the longest summary."""
    for e in payload["embeds"]:
        if len(e["description"]) > EMBED_LIMIT:
            body, _, links = e["description"].partition("\n\n")
            room = EMBED_LIMIT - len(links) - 3
            e["description"] = body[:max(room, 40)].rstrip() + "…\n\n" + links
    for _ in range(80):
        if total_chars(payload) <= MESSAGE_LIMIT:
            break
        for e in reversed(payload["embeds"]):
            body, _, links = e["description"].partition("\n\n")
            rows = links.split("\n") if links else []
            if len(rows) > 1:
                e["description"] = body + "\n\n" + "\n".join(rows[:-1])
                break
        else:
            e = max(payload["embeds"], key=lambda e: len(e["description"]))
            body, _, links = e["description"].partition("\n\n")
            cut = body[: max(40, len(body) // 2)]
            if ". " in cut:
                cut = cut.rsplit(". ", 1)[0]
            e["description"] = cut.rstrip(". ") + ".\n\n" + links
    return payload


def post(payload, webhook, sleep=time.sleep):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                sleep((2, 4)[attempt])
                continue
            raise SystemExit("discord error HTTP %d: %s" % (e.code, body))
        except OSError as e:
            if attempt < 2:
                sleep((2, 4)[attempt])
                continue
            raise SystemExit("discord network error: %s" % e)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("digest", nargs="?")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--failure")
    p.add_argument("--prefix", default="")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    if a.failure:
        date, wd = local_date()
        head = (a.prefix + " " if a.prefix else "") + "⚠️ AI 트렌드 · %s (%s): 오늘은 수집 실패. %s" % (date, wd, a.failure[:1500])
        payload = {"username": "AI Trend", "content": head[:2000], "allowed_mentions": {"parse": []}}
    else:
        if not a.digest:
            p.error("digest path or --failure required")
        with open(a.digest, encoding="utf-8") as f:
            digest = json.load(f)
        problems = validate(digest)
        if problems:
            print("digest invalid:\n  " + "\n  ".join(problems))
            return 1
        if a.validate:
            print("digest ok: %d topics" % len(digest["topics"]))
            return 0
        payload = render(digest, a.prefix)
    if a.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0
    webhook = os.environ.get(ENV, "").strip()
    if not webhook:
        print("send skipped: no webhook (%s unset)" % ENV)
        return 0
    print("posted: HTTP %s" % post(payload, webhook))
    return 0


if __name__ == "__main__":
    sys.exit(main())
