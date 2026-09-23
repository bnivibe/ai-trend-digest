# Taste

What the owner reads to the end. `prompt/digest.md` uses this file when choosing and ordering the five topics. Newest entry last; at most 20 entries; when a new one is added, the oldest is dropped. This is a snapshot of current taste, not an archive.

## The pattern behind the entries

- First-person accounts from practising engineers about how they actually work with agents: the exact prompts, what failed, what they changed. Method over product news.
- The mechanics of agentic work: what context to feed, how to verify (AI judges, evals, mock reviewers), how to structure iteration (scaffolding, harnesses, token budgets).
- Career framing for the AI era from people inside big tech: what separates the top 1%, taste as the moat, learning where the model fails.
- Explanations of how a new kind of model actually works, read against its official documentation and shown wired into code: what it outputs, where it stops, what it hands back to ordinary code or to an LLM. Mechanism and integration, not the launch buzz.
- Release readings that answer what the release means for someone who pays for it: cost per task rather than benchmark rank, whether the higher effort setting is worth it, cache pricing, subscriber limits. Four minutes, one primary source, no hype.
- Korean explainers that track one English primary source (a spec change, an Anthropic engineering post, a Simon Willison or Karpathy piece) and say what it changes in day-to-day work. The value is the reading of the source, not the news itself.
- Claude Code ecosystem internals: MCP spec changes, Skills and how to test them (LLM as a judge, lifecycle, retiring a skill), context management (compact, clear, subagents, rewind), token budgets.
- Reading the shipped artifact itself to find what has not been announced: a binary, a changelog, a spec diff, with the uncertainty stated plainly rather than sold as a scoop.
- The cost mechanics of agent harnesses: prompt caching and KV cache behaviour, what breaks the cache (tool definitions, idle TTL, pruning history), token budgets, and who profits from a cache miss.
- Language is not a filter. Korean-language practitioner content counts as much as English.

## Named interests (the owner's own words, 2026-09-11)

The owner named three things outright: **하네스 (agent harnesses)**, **MCP**, **Claude**. Read them as:

- Harnesses: how coding-agent harnesses are built and compared (Claude Code, Pi, OpenCode, Codex, Hermes, custom ones): tool loading, context handling, caching, cost, evals, where they fail. A harness comparison or a harness internals post outranks a model launch of equal engagement.
- MCP: specification changes, server patterns, stateless transport, tool definition and loading, security, what MCP does and does not replace.
- Claude: Anthropic model releases and behaviour changes, Claude Code features and internals, Anthropic engineering posts, practitioner reports of working with Claude.

A candidate squarely about one of these three takes a slot ahead of a candidate that only matches the general pattern.

## Entries

1. 2026-07-17 · YouTube · 실밸개발자 · AI 시대, 기업이 찾는 상위 1% 인재는 무엇이 다를까? | 메타 시니어 엔지니어의 문제해결법 · https://youtu.be/ViJxFYuVcfs
   Why: a Meta senior engineer replays a hackathon he cleared with agents (60 of 5,300 entrants), prompts shown verbatim. Three questions in order: what to feed (context), how to grade (verification), how to iterate (scaffolding). He built an AI judge and had it review the entry seven times before submitting.
2. 2026-08-15 · YouTube · 실밸개발자 · AI 시대, 메타 엔지니어는 이렇게 일합니다 (커리어 팁 12가지) · https://youtu.be/H3oGKM-pM_Q
   Why: twelve career tips after a year of Claude Code inside Meta. Agentic engineering defined as prompt, context, harness, tokens, evals; learn where AI fails and recalibrate per model; taste as the moat; the 10x to 20x gap already visible inside the company.
3. 2026-03-26 · YouTube · 김플립 - LLM 코딩 · 99%는 프롬프트를 쓰고, 상위 1%는 Skills를 만듭니다 · https://youtu.be/GXE7qn8qMrQ
   Why: Skills as software written in natural language; the difference is in testing (three situations plus LLM as a judge), lifecycle and retiring skills, built on Anthropic's agent-skills engineering post.
4. 2026-04-25 · YouTube · 김플립 - LLM 코딩 · 100만 토큰시대! 앤트로픽이 알려준 클로드코드 컨텍스트 관리법 · https://youtu.be/NpfBwijf0-Y
   Why: the 1M-context trap; four symptoms of a degraded session; how to use compact and clear properly; periodic reminders; subagents and rewind. Practical mechanics from Anthropic's own guidance.
5. 2026-05-04 · YouTube · 김플립 - LLM 코딩 · 꼭 알아야할 안드레 카파시 30분 인터뷰 완전정리 · https://youtu.be/UNnsS03whx0
   Why: a structured reading of a Karpathy interview: Software 1.0 to 3.0, jagged intelligence (genius only where grading is possible), vibe coding versus agentic engineering, what humans must still do better, thinking can be outsourced but understanding cannot.
6. 2026-09-01 · YouTube · 김플립 - LLM 코딩 · 죽어가던 MCP 심폐소생 시작됐나? Stateless에 주목해야 할 이유 · https://youtu.be/3C-JE5vcrsg
   Why: reads the 2026-07-28 MCP spec change (stateless, request-response like REST) through Simon Willison's post: why held connections were the problem, serverless economics, no backward compatibility, and the answer to "isn't it just an API wrapper".
7. 2026-07-24 · LinkedIn · Jeongmin Lee (jyoung105) · 코딩 에이전트 비용을 줄이고 싶다면, prompt caching 구조를 알아야 합니다 · https://www.linkedin.com/posts/jyoung105_activity-7486263712614555648-4f7a
   Why: a Korean reading of Armin Ronacher's post on how the Pi coding agent uses prompt caching, cut to five points: changing one tool definition invalidates the whole cache, the 5-minute TTL, one cache miss is the most expensive event in a session, pruning history costs more than it saves, and gateways earn more on misses. Agentic mechanics plus cost, from a primary source.
8. 2026-09-16 · YouTube (Short) · 김플립 - LLM 코딩 · 클로드코드 /limit-reset 다음 버전, 바이너리 까보니 이미 들어있습니다 · https://youtube.com/shorts/htC7_Ay2Qy4
   Why: found the unreleased `/limit-reset` command inside the Claude Code v2.1.273 binary and said outright that reading the binary guarantees nothing. Two minutes, one concrete finding, no overclaim. Shorts count: format is not a filter, the subject is.
9. 2026-09-22 · YouTube · Claudical · Claude Opus 5.5 나왔습니다 | 성능, 가격, 말투 4분 정리 · https://youtu.be/vy7USjgHvbI
   Why: a four-minute reading of Anthropic's Opus 5.5 announcement built around the questions a paying user has: cost per problem (the taxi-meter framing), whether max effort beat the default, cache read pricing, the two benchmarks lost to GPT-6 Astra, and what changes for Pro, Max and Team limits. Same day as the release, one primary source linked.
10. 2026-09-18 · YouTube · 편집자P · [시즌 3] Jev란 무엇인가? · https://youtu.be/mDnbjbjosFY
   Why: explains Jev, the decision model that scores instead of generating, by reading its official docs: the three outputs (Choice, Score, Noul), why an LLM keeps emitting text even when it only needs to judge, a support-ticket router that splits team, complaint and urgency in one pass, and a game demo where Jev gives a probability and existing code decides whether to act. Frames it as a complement to LLMs, not a replacement.
