# ai-trend-digest

Daily AI developer trend digest, posted to Discord at 07:00 America/Vancouver by a Claude cloud routine.
Design: Google Drive `프로젝트/ai-trend-digest/2026-09-09-design.md`. This file is the runbook only.

## How it works

1. `python3 collect.py` pulls candidates from five sources without login (YouTube search + channel RSS, X syndication timelines, Hacker News Algolia, GitHub trending, Reddit hot RSS) into `out/candidates.json`.
2. Claude follows `prompt/digest.md` to cluster them into five topics in `out/digest.json`.
3. `python3 post_discord.py out/digest.json` renders one webhook message with five embeds. `--failure "reason"` posts a failure notice instead. The channel is never silent.

Standard library only, Python 3.9 compatible. Sources run in parallel threads under a time budget (`budget_seconds` in config, default 240): a host that fails twice at the network level, or exhausts its retries on HTTP 429, is skipped for the rest of the run, and any fetch attempted after the deadline is skipped, so a blocked host costs under a minute instead of stalling the run.

## Run locally

```bash
python3 -m unittest discover -s tests -v          # parser tests against captured fixtures
python3 collect.py --probe                        # one GET per host
python3 collect.py --dry-run                      # top candidates per source, writes nothing
python3 collect.py --out out/candidates.json
# write out/digest.json following prompt/digest.md (the local skill /ai-trend-digest does this)
python3 post_discord.py --validate out/digest.json
. ~/.claude/secrets.env && python3 post_discord.py out/digest.json --prefix "[TEST]"
```

The webhook is read only from `AI_TREND_DISCORD_WEBHOOK`. Locally it lives in `~/.claude/secrets.env` (`export AI_TREND_DISCORD_WEBHOOK=...`). Never put it in a file in this repository.

## Configuration

`config.json` is the only file to edit: YouTube queries and channel ids, X accounts, HN keywords and minimum points, GitHub keywords, subreddits, window (`hours`), caps and thresholds. Channel ids resolve from a YouTube channel-filtered search (`results?search_query=<name>&sp=EgIQAg%3D%3D`) by reading `channelRenderer.channelId`.

## Routine operations

- Routine name: `AI Trend Digest (daily 07:00 Vancouver)`; message = `prompt/routine.md` verbatim; environment: Default Cloud Environment; model claude-sonnet-5.
- Cron is UTC. `0 14 * * *` = 07:00 PDT. **After 2026-11-01 change it to `0 15 * * *`** (07:00 PST), and back on 2027-03-14.
- The webhook must exist as the environment variable `AI_TREND_DISCORD_WEBHOOK` in the cloud environment.
- "Why did it not arrive": the local skill `/ai-trend-digest` reads the routine's run logs (RemoteTrigger `list_runs`, `get_run_log`). No message and no failure notice means the routine did not fire or could not reach Discord.

## Troubleshooting

- `parser_suspect` for a source: the page structure changed. Capture the new response (commands below), add it to `tests/fixtures/`, fix the parser, run the tests, open a PR.
- X `stale`: the syndication cache for that account is frozen (six of the fourteen configured accounts were stale on 2026-09-09); nothing to fix, the account simply contributes nothing. Remove it from `config.json` if it stays stale for weeks.
- Reddit `HTTP 429`: rate limited per IP; calls are already spaced 3 s, and running `--probe` right before a collect triggers it. It clears on the next run.
- Discord `HTTP 400`: the error body names the limit; `enforce_budget` should prevent it, so treat it as a bug and add a test.
- YouTube search returns nothing in the cloud but works locally: datacenter IP treatment; keep the channel RSS path (it is plain XML) and open an issue.

## Re-capturing fixtures

```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
curl -sS -A "$UA" -H "Accept-Language: en-US,en;q=0.9" "https://www.youtube.com/results?search_query=AI+agents&sp=EgIIAg%3D%3D&hl=en&gl=US" | gzip > tests/fixtures/youtube_search_today_en.html.gz
curl -sS -A "$UA" "https://www.youtube.com/feeds/videos.xml?channel_id=UCrDwWp7EBBv4NwvScIpBDOA" | gzip > tests/fixtures/youtube_channel_rss_anthropic.xml.gz
curl -sS -A "$UA" "https://syndication.twitter.com/srv/timeline-profile/screen-name/AnthropicAI" | gzip > tests/fixtures/x_timeline_fresh_anthropicai.html.gz
curl -sS -A "$UA" "https://cdn.syndication.twimg.com/tweet-result?id=2079195918595764300&token=a" | gzip > tests/fixtures/x_tweet_result.json.gz
curl -sS "https://hn.algolia.com/api/v1/search?query=AI&tags=story&numericFilters=points%3E50&hitsPerPage=10" | gzip > tests/fixtures/hn_algolia_ai_24h.json.gz
curl -sS -A "$UA" "https://github.com/trending?since=daily" | gzip > tests/fixtures/github_trending_daily.html.gz
curl -sS -A "$UA" "https://www.reddit.com/r/ClaudeAI/hot.rss?limit=10" | gzip > tests/fixtures/reddit_claudeai_hot.rss.gz
```

After re-capturing, update the literal values asserted in the tests (video id, counts, dates) to the new fixture.
