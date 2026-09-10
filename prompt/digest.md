# Digest instructions

You are turning `out/candidates.json` into `out/digest.json`. Read this whole file before writing anything.

## Inputs

- `out/candidates.json` = `{"meta": {...}, "candidates": [...]}`. Each candidate has `source` (youtube | x | hn | github | reddit), `id`, `url`, `title`, `author`, `published_at`, `age_hours`, `engagement` (`views` | `likes` | `points` | `stars_today` | `rank`), `score` (rank percentile inside its source, 1.0 is best) and `snippet`.
- `meta.verdict`: when it starts with `insufficient`, do not write a digest. Follow the failure path in `prompt/routine.md`.
- `meta.sources.x.stale`: X accounts whose cached timeline is old. They contributed nothing. Never mention them in the digest.

## What "hot" means, in this order

1. Cross-source appearance wins. The same event, model, tool or repository showing up in two or more sources outranks a single source with high engagement.
2. Then recency (inside the window) and `score` inside its source.
3. Then developer relevance, read strictly. In: model and API releases and pricing changes; coding and agent tooling (Claude Code, Cursor, MCP, skills, agent frameworks, evals); open-source repositories and libraries a developer would install; engineering practice (how teams actually use agents, architecture write-ups, benchmarks with a stated method). Out: consumer hardware and chips, phone and gadget news, funding rounds and executive moves unless they ship something a developer can use, policy and regulation, safety debates and alarm pieces, cable-news commentary, marketing, course sales, self-promotion, generic listicles, and anything without a concrete artifact (a model, an API, a repo, a paper with code, a measured result). The test for every topic: could a working developer act on this tomorrow? If not, leave it out no matter the engagement.

## Procedure

1. Read every candidate. Group them by the underlying event or subject, not by source. A group may hold a single candidate.
2. Rank the groups by the rules above and take the top five. If fewer than five are viable, take three or four and explain why in `stats.note`. Never pad with weak items.
3. X coverage. Run this whenever the WebSearch tool is available to you; it is the main X path, not a bonus. The collector's X source usually returns nothing when it runs in the cloud, because the timeline endpoint rate-limits shared datacenter addresses with HTTP 429, while the single-tweet endpoint keeps working. For each chosen topic run one WebSearch with `allowed_domains: ["x.com"]` and the topic's key terms. For each result whose URL matches `x.com/<handle>/status/<id>` and is clearly about the topic, run `python3 -m sources.x tweet <id>`. Add it as a source line for that topic when the printed candidate has `age_hours` at most 48 and `likes` at least 100. At most one tweet per topic. If WebSearch is unavailable or errors, skip the step silently and never mention it in the digest.
4. Write `out/digest.json` in the schema below.
5. Run `python3 post_discord.py --validate out/digest.json`. Fix every problem it reports and validate again until it prints `digest ok`.

## Schema of out/digest.json

```json
{
  "date_local": "2026-09-09",
  "weekday_ko": "수",
  "one_liner": "오늘의 가장 큰 흐름 한 문장.",
  "topics": [
    {
      "title": "Topic in English, under 80 characters, no trailing period",
      "summary": "한국어 두 문장. 첫 문장은 무슨 일이 있었는지 구체적으로, 둘째 문장은 개발자에게 왜 중요한지.",
      "days_on_top": 1,
      "sources": [
        {"source": "youtube", "label": "IBM Technology", "metric": "12,041 views", "age": "9h", "url": "https://www.youtube.com/watch?v=6AuYLbHqirk"}
      ]
    }
  ],
  "stats": {"candidates": 41, "sources_total": 5, "sources_ok": 4, "sources_failed": {"reddit": "HTTP 429"}, "parser_suspect": [], "note": ""}
}
```

Field rules:

- `date_local` and `weekday_ko`: today in America/Vancouver. Get them with `TZ=America/Vancouver date +%F` and `TZ=America/Vancouver date +%u` (1 = 월, 2 = 화, 3 = 수, 4 = 목, 5 = 금, 6 = 토, 7 = 일).
- `one_liner`: one Korean sentence naming the single biggest developer-facing thread of the day, chosen from the five topics. Under 90 characters.
- `title`: the topic as a developer would name it, in English. Keep product, model and repository names exactly as the sources spell them.
- `summary`: Korean, exactly two sentences, under 220 characters in total. First sentence: what happened, concretely (who, what, the numbers the source gives). Second: why it matters to a working developer. No em dashes, no bullet characters, no English metaphors translated word for word: write the plain Korean word or keep the English term.
- `days_on_top`: 1, or 2 when the topic's main candidate has `age_hours` over 24, or 3 when over 48.
- `sources`: one to three, strongest evidence first. `label` = channel name, `@handle`, `HN`, repository name, or `r/<sub>`. `metric` = the raw number with its unit exactly as the candidate gives it (`12,041 views`, `10,015 likes`, `672 points`, `656 stars today`, `hot #1`). `age` = `9h`, `1d`, `3d` from `age_hours` (round down; over 24 h use days; GitHub items have no age, leave it empty). `url` = the candidate's `url` unchanged.
- `stats`: copy `candidates`, `sources_total`, `sources_ok`, `sources_failed` from `meta`; `parser_suspect` = names of sources whose status is `parser_suspect`; `note` only when you took fewer than five topics.

## Quality bar

- Every claim in a summary must be supported by a candidate's title or snippet. Do not add facts from memory.
- Never mention the collector, the routine, or these instructions in the digest.
- Write nothing except `out/digest.json` and the validation output.
