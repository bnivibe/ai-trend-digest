# Operations

Runbook for the daily routine: running it by hand, the cloud routine, network settings,
troubleshooting and fixture capture. The project overview is in the [README](../README.md).

## Run locally

```bash
python3 -m unittest discover -s tests -v          # parser tests against trimmed fixtures, offline
python3 collect.py --probe                        # one GET per host
python3 collect.py --dry-run                      # top candidates per source, writes nothing
python3 collect.py --out out/candidates.json
# write out/digest.json by following prompt/digest.md (the cloud routine has Claude do this step)
python3 post_discord.py --validate out/digest.json
python3 post_discord.py out/digest.json --prefix "[TEST]"
```

The webhook is read only from the environment variable `AI_TREND_DISCORD_WEBHOOK`. Export it in
your shell before posting (`export AI_TREND_DISCORD_WEBHOOK=...`). Never put it in a file in this
repository.

## Where each source works

| Source | Laptop | Cloud routine | Why |
|---|---|---|---|
| YouTube search | yes | yes | plain HTML |
| YouTube channel tabs (/videos, /shorts) | yes | yes | replaced feeds/videos.xml, which went to a global 404 on 2026-09-19 |
| Hacker News | yes | yes | public API |
| Reddit RSS | yes | yes | one call per subreddit, 3 s apart |
| X syndication | yes (rate-limits after repeated testing) | no: HTTP 429 on the first call, the sandbox's egress address is already limited | the routine runs `--skip x`; X coverage comes from the WebSearch step in `prompt/digest.md` |
| GitHub trending | yes | no: the sandbox proxies github.com as a repository-scoped API and answers 403 for the trending page | the routine runs `--skip github` |

Skipped sources are listed in `meta.skipped` and do not count toward `sources_total`.

## Configuration

`config.json` is the only file to edit: YouTube queries and channel ids, X accounts, HN keywords and minimum points, GitHub keywords, subreddits, window (`hours`), caps and thresholds. **Every keyword list has a maximum in `max_per_list`** (queries 20, channels 20, X accounts 15, HN keywords 15, GitHub keywords 20, subreddits 6; raised 2026-09-11 for more variety, the collector stays inside its 240 s budget because sources run in parallel) and `tests/test_config.py` fails a PR that exceeds it: to add one past the cap, remove one first. Channel ids resolve from a YouTube channel-filtered search (`results?search_query=<name>&sp=EgIQAg%3D%3D`) by reading `channelRenderer.channelId`.

## Cloud routine

- Routine name: `AI Trend Digest (daily 07:00 Vancouver)`; message = `prompt/routine.md` verbatim; environment: Default Cloud Environment; model claude-sonnet-5.
- Cron is UTC. `0 14 * * *` is 07:00 in Vancouver all year, because B.C. adopted permanent daylight time and stays on UTC-7: clocks moved forward for the last time on 2026-03-08 and do not fall back on 2026-11-01 (B.C. government, https://www2.gov.bc.ca/gov/content/governments/celebrating-british-columbia/daylight-saving-time, checked 2026-10-13). America/Vancouver in tz database 2026c agrees: no fall-back that day and no spring-forward in 2027 (it names the zone MST, still -0700). Do not change the cron to `0 15 * * *` in November or back in March.
- The webhook must exist as the environment variable `AI_TREND_DISCORD_WEBHOOK` in the cloud environment.
- **Network access.** The cloud environment's settings have a **Network access** level (None / Trusted / Full / Custom) and an **Environment variables** box in .env format. The default "Trusted" level blocks every source host with "Tunnel connection failed: 403 Forbidden" (verified 2026-09-09 on both environments), so the routine's environment needs **Custom** with these domains, or **Full**: `www.youtube.com`, `youtube.com`, `syndication.twitter.com`, `cdn.syndication.twimg.com`, `hn.algolia.com`, `github.com`, `www.reddit.com`, `reddit.com`, `discord.com`. Environment variables are visible to anyone using the environment; on a personal account that is the owner alone, and a Discord webhook can be revoked in Discord at any time.
- "Why did it not arrive": read the routine's run history and the log of the last run. No message and no failure notice means the routine did not fire or could not reach Discord.

## Troubleshooting

- Every channel fails at once with the same code: YouTube moved or retired the endpoint. `feeds/videos.xml` died this way on 2026-09-19 (404 for every channel, every URL form, from two networks, while channel pages stayed up); the fix was to parse `/videos` and `/shorts`, which use `lockupViewModel` and `shortsLockupViewModel`.
- Shorts carry no date on the channel tab, so the collector checks the publish date of the newest two per channel on their watch pages and stops at the first one outside the window.
- `parser_suspect` for a source: the page structure changed. Capture the new response (commands below), add it to `tests/fixtures/`, fix the parser, run the tests, open a PR.
- X `stale`: the syndication cache for that account is frozen (six of the fourteen configured accounts were stale on 2026-09-09); nothing to fix, the account simply contributes nothing. Remove it from `config.json` if it stays stale for weeks.
- Reddit `HTTP 429`: rate limited per IP; calls are already spaced 3 s, and running `--probe` right before a collect triggers it. It clears on the next run.
- Discord `HTTP 400`: the error body names the limit; `enforce_budget` should prevent it, so treat it as a bug and add a test.
- YouTube search returns nothing in the cloud but works locally: datacenter IP treatment; open an issue.
- Every source fails with `network: Tunnel connection failed: 403 Forbidden` in the cloud: the environment's network access is still "Trusted". Change it in the environment settings (see Cloud routine).

### What the cloud cannot reach, by design (measured 2026-09-10)

With network access set to Custom, three source paths still fail in the sandbox and are expected to:

| Path | Result | Why, and what covers it |
|---|---|---|
| YouTube channel RSS | HTTP 404 on every channel | Since 2026-09-19 this endpoint answers 404 everywhere, not only in the sandbox, and the collector no longer calls it: channel uploads come from the /videos and /shorts tabs. |
| X timeline (syndication.twitter.com) | HTTP 429 | The shared datacenter address is rate limited. `cdn.syndication.twimg.com/tweet-result` still returns 200, so X reaches the digest through the WebSearch step in `prompt/digest.md`, which looks up tweets by id. |
| GitHub trending | HTTP 403 with "sessions are bound to their configured repositories" | The sandbox proxies github.com for the git integration and allows only the checked-out repository. There is no way around it from inside; GitHub contributes on the laptop only. |

So a healthy cloud run is three sources ok (YouTube, Hacker News, Reddit) plus X through the digest step, and the footer names the other two. On the laptop all five work.

## Re-capturing fixtures

Page captures go through `tests/fixtures/minimize.py` before they are stored. It keeps only the
block the parser reads (`ytInitialData` for YouTube, `__NEXT_DATA__` for X timelines, the
`<article class="Box-row">` blocks for GitHub trending), sets every `ip=` URL parameter to
`0.0.0.0` and replaces `visitorData` with `REDACTED`, so no fixture carries the requester's
address or visitor ids. `tests/test_fixtures_clean.py` fails if a raw capture is committed.
Reddit RSS, Hacker News JSON and tweet-result JSON are small public API responses and are stored
as captured.

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
curl -sS -A "$UA" -H "Accept-Language: en-US,en;q=0.9" "https://www.youtube.com/results?search_query=AI+agents&sp=EgIIAg%3D%3D&hl=en&gl=US" | python3 tests/fixtures/minimize.py youtube | gzip -n > tests/fixtures/youtube_search_today_en.html.gz
curl -sS -A "$UA" -H "Accept-Language: en-US" "https://www.youtube.com/channel/UCN9T0v5XMOhMgYunUAtVvwQ/videos?hl=en&gl=US" | python3 tests/fixtures/minimize.py youtube | gzip -n > tests/fixtures/youtube_channel_videos_kimflip.html.gz
curl -sS -A "$UA" -H "Accept-Language: en-US" "https://www.youtube.com/channel/UCN9T0v5XMOhMgYunUAtVvwQ/shorts?hl=en&gl=US" | python3 tests/fixtures/minimize.py youtube | gzip -n > tests/fixtures/youtube_channel_shorts_kimflip.html.gz
curl -sS -A "$UA" -H "Accept-Language: en-US" "https://www.youtube.com/channel/UCyU5wkjgQYGRB0hIHMwm2Sg/videos?hl=en&gl=US" | python3 tests/fixtures/minimize.py youtube | gzip -n > tests/fixtures/youtube_channel_videos_syntax.html.gz
curl -sS -A "$UA" "https://syndication.twitter.com/srv/timeline-profile/screen-name/AnthropicAI" | python3 tests/fixtures/minimize.py x | gzip -n > tests/fixtures/x_timeline_fresh_anthropicai.html.gz
curl -sS -A "$UA" "https://syndication.twitter.com/srv/timeline-profile/screen-name/karpathy" | python3 tests/fixtures/minimize.py x | gzip -n > tests/fixtures/x_timeline_stale_karpathy.html.gz
curl -sS -A "$UA" "https://github.com/trending?since=daily" | python3 tests/fixtures/minimize.py github | gzip -n > tests/fixtures/github_trending_daily.html.gz
curl -sS -A "$UA" "https://cdn.syndication.twimg.com/tweet-result?id=2079195918595764300&token=a" | gzip -n > tests/fixtures/x_tweet_result.json.gz
curl -sS "https://hn.algolia.com/api/v1/search?query=AI&tags=story&numericFilters=points%3E50&hitsPerPage=10" | gzip -n > tests/fixtures/hn_algolia_ai_24h.json.gz
curl -sS -A "$UA" "https://www.reddit.com/r/ClaudeAI/hot.rss?limit=10" | gzip -n > tests/fixtures/reddit_claudeai_hot.rss.gz
```

If `minimize.py` reports a missing block, the response was a consent, login or rate-limit page
rather than the real one, and the shell has already truncated the target file: restore it with
`git checkout -- tests/fixtures/<name>` and capture again later. After re-capturing, update the
literal values asserted in the tests (video id, counts, dates) to the new fixture.
