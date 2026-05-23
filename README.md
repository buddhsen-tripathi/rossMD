# Ross — The Pre-Lawyer

Multi-agent NY legal associate. Drop in a situation; Ross spins up Intake →
Issue Spotter → Researchers (fan-out) → Strategist → Adversary → Drafter ⇄
Harvey and returns a cited brief, the weapons, a draft, the adversary's best
shot, and Harvey's terse take — live, in ~90 seconds.

## Stack
- **OpenRouter** — every agent brain (Gemini Pro for the thinkers, Flash for the workers)
- **ClickHouse** — corpus + vector index + blackboard + audit trail (one store, four jobs)
- **fastembed / BGE-small** — local 384-dim embeddings (no API, validated)
- **CourtListener** — NY case law (free token)
- **Nimble** — anti-bot scraping for statute/admin-code sites
- **Datadog** — traces every agent event (no-op without key)
- **Next.js 16** — dark, dense Agent Theater UI

## Setup
The only credential you actually need is **`OPENROUTER_API_KEY`** (the agent
brains). ClickHouse runs locally in Docker — no signup. Case law comes from the
open Caselaw Access Project — no token.

1. `cp .env.example .env`. Defaults already point at local ClickHouse
   (`localhost:8123`, user `default`, pass `ross_local`). Add your
   `OPENROUTER_API_KEY`. Optional: `NIMBLE_API_KEY` (verbatim statute text),
   `DD_API_KEY` (observability). To use ClickHouse Cloud instead, swap
   `CLICKHOUSE_HOST/PORT/PASSWORD` and set `CLICKHOUSE_SECURE=true`.
2. Bring up the corpus + run:
   ```
   make bringup     # ch-up → db → scrape (CAP) → ingest (embed locally)
   make api         # backend on :8000
   make web         # frontend on :3000
   ```

## Layout
```
ross/
  config.py           env
  store.py            ClickHouse schema + vector_search
  embed.py            local BGE embeddings
  llm.py              OpenRouter client (traced)
  orchestrator.py     the agent dance (hand-written, no framework)
  trace.py            Datadog
  server.py           FastAPI: /api/stream (SSE), /api/doc, /api/replay
  agents/prompts.py   the personalities  ← the product
  corpus/
    courtlistener.py  NY case law
    statutes.py       NY statutes via Nimble
    ingest.py         JSONL → chunks → embeddings → ClickHouse
data/raw/             scraped + seeded JSONL
web/                  Next.js Agent Theater
```

## Demo safety
Every live run persists its trace to ClickHouse `traces`. Replay any run with
zero LLM calls: `GET /api/replay/{run_id}` (UI animates identically). Pre-warm
one rehearsed scenario and keep its run_id for the fallback.
