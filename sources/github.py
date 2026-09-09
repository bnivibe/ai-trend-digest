"""GitHub trending (daily) HTML page. No auth. Age is unknown by design: the daily list is 'today'."""
import html as htmllib
import re

from .common import FetchError, assign_scores, candidate, fetch, parse_count, result

URL = "https://github.com/trending?since=daily"
_ARTICLE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
_REPO = re.compile(r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"', re.S)
_DESC = re.compile(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', re.S)
_LANG = re.compile(r'itemprop="programmingLanguage">([^<]+)')
_TODAY = re.compile(r'([\d,]+)\s+stars today')
_TOTAL = re.compile(r'href="/[^"]+/stargazers"[^>]*>(.*?)</a>', re.S)


def _clean(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def parse_trending_html(html):
    rows = []
    for art in _ARTICLE.findall(html):
        repo = _REPO.search(art)
        if not repo:
            continue
        desc, lang, today, total = _DESC.search(art), _LANG.search(art), _TODAY.search(art), _TOTAL.search(art)
        rows.append({"path": repo.group(1),
                     "description": _clean(desc.group(1)) if desc else "",
                     "language": lang.group(1).strip() if lang else "",
                     "stars_today": parse_count(today.group(1)) if today else 0,
                     "stars_total": parse_count(_clean(total.group(1))) if total else None})
    return rows


def is_ai_repo(item, keywords):
    hay = (item["path"] + " " + item["description"]).lower()
    return any(re.search(r"\b" + re.escape(k.lower()) + r"\b", hay) for k in keywords)


def collect(config, now, hours, sleep=None):
    cfg = config["github"]
    cap = config.get("per_source_cap", 8)
    try:
        rows = parse_trending_html(fetch(URL))
    except FetchError as e:
        return result([], False, errors={"trending": str(e)})
    items = []
    for r in rows:
        if not is_ai_repo(r, cfg.get("keywords", [])):
            continue
        name = r["path"].strip("/")
        snippet = "%s. %s stars today, %s total. %s" % (r["description"], r["stars_today"], r["stars_total"], r["language"])
        items.append(candidate("github", name, "https://github.com" + r["path"], name, name.split("/")[0],
                               None, None, {"stars_today": r["stars_today"]}, snippet))
    assign_scores(items, lambda it: it["engagement"]["stars_today"])
    return result(items[:cap], True, fetched=len(rows))
