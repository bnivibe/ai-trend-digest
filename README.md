# ai-trend-digest

A daily AI-for-developers news digest. It collects the last 24 hours from five public
sources, has Claude group and rank them into five topics, and posts the result to Discord
every morning at 07:00 Vancouver time. It has run unattended as a scheduled Claude Code
cloud routine since September 2026.

## How it works

1. `collect.py` gathers candidates without logging in from YouTube (search, channel
   uploads and Shorts), X, Hacker News, GitHub trending and Reddit, scores them, and writes
   `out/candidates.json`.
2. A Claude routine follows `prompt/digest.md`: stories that several sources agree on rank
   first, then a short taste file (`prompt/taste.md`) breaks ties. It writes five topics
   with two-sentence Korean summaries.
3. `post_discord.py` checks the result against Discord's size limits and posts one webhook
   message with five embeds. If collection fails it posts a failure notice instead, so the
   channel is never silent.

## Design choices

- Python standard library only (3.9+), so the cloud sandbox installs nothing.
- Sources run in parallel threads under one time budget (240 s). A host that fails twice
  at the network level, or keeps answering HTTP 429, is skipped for the rest of the run, so
  one blocked site costs seconds instead of stalling the run.
- Each source is isolated. A malformed page marks that source as failed and the run
  continues with the others.
- Every keyword list in `config.json` has a cap, enforced by a test.
- The Discord webhook is read only from an environment variable and never stored in the
  repository.
- 79 unit tests run offline against [trimmed captures](tests/fixtures/minimize.py) of real
  responses.

## What broke, and what changed

- YouTube's channel RSS feed began returning 404 for every channel on 2026-09-19. The
  collector now reads each channel's /videos and /shorts pages instead.
- In the cloud sandbox, X rate-limits the shared outbound address and github.com is
  restricted to repository-scoped API calls. The routine skips those two sources and covers
  X through a web search step in the digest prompt.

## Run it

```bash
python3 -m unittest discover -s tests
python3 collect.py --dry-run
```

Operations notes (cloud routine, network settings, troubleshooting, fixture capture) are in
[docs/operations.md](docs/operations.md).

## License

MIT, see [LICENSE](LICENSE).
