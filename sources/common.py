"""Shared helpers for all sources: HTTP fetch, time parsing, counting, scoring, candidate shape."""
import gzip
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
RETRY_STATUS = (429, 500, 502, 503, 504)
BACKOFF = (2, 4, 8)
NETWORK_ATTEMPTS = 2      # attempts on network-level errors (DNS, refused, timeouts); HTTP 429/5xx get `retries`
DEAD_AFTER_FAILURES = 2   # network failures on a host before the rest of its URLs are skipped this run

_LOCK = threading.Lock()
_HOST_FAILURES = {}
_DEADLINE = [None]


def reset_run(deadline=None):
    """Call once per run: forget dead hosts and set the time budget (epoch seconds, or None for no budget)."""
    with _LOCK:
        _HOST_FAILURES.clear()
    _DEADLINE[0] = deadline


def _host(url):
    return urllib.parse.urlsplit(url).hostname or url


def _note_network_failure(host):
    with _LOCK:
        _HOST_FAILURES[host] = _HOST_FAILURES.get(host, 0) + 1


def _mark_host_dead(host):
    with _LOCK:
        _HOST_FAILURES[host] = DEAD_AFTER_FAILURES


def _host_is_dead(host):
    with _LOCK:
        return _HOST_FAILURES.get(host, 0) >= DEAD_AFTER_FAILURES


class FetchError(Exception):
    """Raised after retries are exhausted. str(e) is a short reason like 'HTTP 429',
    with a brief server explanation appended when one is available."""


def _hint(e):
    """A short, safe explanation from an error body, or ''. Keeps daily footers readable."""
    try:
        body = e.read(400).decode("utf-8", "replace")
    except Exception:
        return ""
    m = re.search(r'"message"\s*:\s*"([^"]{5,160})"', body)
    if m:
        return " (%s)" % m.group(1).strip()
    if "<html" in body[:200].lower():
        return ""
    text = re.sub(r"\s+", " ", body).strip()
    return " (%s)" % text[:120] if text else ""


def fetch(url, timeout=20, retries=3, headers=None, sleep=time.sleep, optional=False):
    """GET url and return the body as text. Retries on 429/5xx and network errors, honouring Retry-After.

    optional=True marks a secondary path: its failures are still raised, but they do not count
    toward the per-host circuit breaker, so a blocked extra endpoint cannot take the host's
    primary endpoints down with it."""
    hdrs = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    host = _host(url)
    if _host_is_dead(host):
        raise FetchError("skipped: %s unreachable earlier this run" % host)
    reason = "unknown"
    for attempt in range(retries):
        if _DEADLINE[0] is not None and time.time() > _DEADLINE[0]:
            raise FetchError("skipped: time budget exhausted")
        req = urllib.request.Request(url, headers=hdrs)
        wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            reason = "HTTP %d" % e.code
            if e.code not in RETRY_STATUS:
                raise FetchError(reason + _hint(e))
            if e.code == 429 and attempt == retries - 1 and not optional:
                _mark_host_dead(host)  # a rate limit is host-wide: stop hammering it for the rest of the run
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after and str(retry_after).isdigit():
                wait = max(wait, min(int(retry_after), 30))
        except (urllib.error.URLError, OSError) as e:
            reason = "network: %s" % getattr(e, "reason", e)
            if attempt + 1 >= NETWORK_ATTEMPTS:  # give up on network errors sooner than on HTTP errors
                if not optional:
                    _note_network_failure(host)
                raise FetchError(reason)
        if attempt < retries - 1:
            sleep(wait)
    raise FetchError(reason)


_REL = re.compile(r"(\d+)\s*(mo|s|m|h|d|w|y|sec|min|hr|second|minute|hour|day|week|month|year)s?\s*ago", re.I)
_SHORT = re.compile(r"^\s*(\d+)\s*(mo|y|w|d|h|m)\s*$", re.I)
_UNIT_HOURS = {"s": 1 / 3600, "sec": 1 / 3600, "second": 1 / 3600,
               "m": 1 / 60, "min": 1 / 60, "minute": 1 / 60,
               "h": 1.0, "hr": 1.0, "hour": 1.0, "d": 24.0, "day": 24.0, "w": 168.0, "week": 168.0,
               "mo": 720.0, "month": 720.0, "y": 8760.0, "year": 8760.0}


def relative_age_hours(text):
    """'9h ago', '1d ago', 'Streamed 3 hours ago', '2 weeks ago', '6mo' -> hours; None if unparseable."""
    if not text:
        return None
    m = _REL.search(text) or _SHORT.match(text)
    if not m:
        return None
    return int(m.group(1)) * _UNIT_HOURS[m.group(2).lower()]


_COUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMmBb])?(?![A-Za-z])")


def parse_count(text):
    """'104,604 views' -> 104604; '1.2M' -> 1200000; '12K' -> 12000; 'No views' -> None."""
    if not text:
        return None
    m = _COUNT.search(text.replace(" ", " "))
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[(m.group(2) or "").upper()]
    return int(num * mult)


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text):
    """Accepts '2026-09-08T14:05:57Z' and '2026-09-09T18:29:00+00:00'. Returns an aware UTC datetime."""
    if not text:
        return None
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hours_between(later, earlier):
    return (later - earlier).total_seconds() / 3600.0


def candidate(source, id_, url, title, author, published_at, age_hours, engagement, snippet=""):
    """The normalized candidate shape from the spec (section 4)."""
    eng = {"views": None, "likes": None, "points": None, "stars_today": None, "reactions": None, "rank": None}
    eng.update(engagement)
    return {"source": source, "id": str(id_), "url": url, "title": (title or "").strip()[:200],
            "author": author, "published_at": published_at,
            "age_hours": None if age_hours is None else round(age_hours, 1),
            "engagement": eng, "score": 0.0,
            "snippet": re.sub(r"\s+", " ", snippet or "").strip()[:300]}


def assign_scores(items, metric):
    """Rank percentile within the batch: best item scores 1.0, worst 1/n. Sorts items descending in place."""
    n = len(items)
    if n == 0:
        return items
    order = sorted(range(n), key=lambda i: (metric(items[i]) or 0), reverse=True)
    for rank, idx in enumerate(order):
        items[idx]["score"] = round((n - rank) / n, 3)
    items.sort(key=lambda it: it["score"], reverse=True)
    return items


def result(items, fetched_ok, **notes):
    """What every source's collect() returns."""
    return {"items": items, "fetched_ok": fetched_ok, "notes": notes}
