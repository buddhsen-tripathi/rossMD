# Ross MD — Team Onboarding

The pre-lawyer for healthcare regulatory work. Drop in an arrangement, a CID, a
breach, an ED transfer; a team of agents reads everything, finds every statute,
safe harbor, and OIG opinion, and produces cited work product — structured so
the government never asks the question.

The corpus + agent runs live in **ClickHouse Cloud (shared)**, so you don't need
to re-scrape or re-ingest anything. You run the backend + frontend locally and
point them at the shared Cloud.

## Prerequisites
- **uv** (Python) — https://docs.astral.sh/uv/
- **Node 18+** (the `web/` frontend)
- An **OpenRouter API key** (your own) — https://openrouter.ai/keys

## Setup (≈3 minutes)
```bash
git clone <repo> && cd ross
uv sync                       # python deps
npm install --prefix web      # frontend deps
cp .env.example .env          # then fill it in (next step)
```

Fill `.env`:
```
OPENROUTER_API_KEY=<your own key>          # required — the agent brains

# shared ClickHouse Cloud (ask the team lead for the host + password)
CLICKHOUSE_HOST=<shared cloud host>.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=<shared cloud password>
CLICKHOUSE_DATABASE=ross
CLICKHOUSE_SECURE=true

# optional
NIMBLE_API_KEY=     # gov-site scraping + Tier-2 web fetch for cites missing from the corpus
DD_API_KEY=         # Datadog tracing
```

## Run
```bash
make api      # FastAPI on :8000  (the agent orchestrator + SSE)
make web      # Next.js on :3000
```
Open **http://localhost:3000**. Hit **"See it work"** / a scenario card to run
live (~80s), or **"Replay recorded run"** for the fast deterministic demo.
`GET /api/health` shows which creds are live.

## How it's built
- `ross/orchestrator.py` — the agent dance (Intake → Issue Spotter → Researchers
  fan-out → Strategist → Adversary → Drafter ⇄ Harvey). **No framework** — this
  is the product; spend your time here.
- `ross/agents/prompts.py` — the personalities. Tuning these is high-leverage.
- `ross/llm.py` — OpenRouter client. Workers run Flash w/o thinking; the
  "deep" agents run Flash w/ low reasoning. Hard 30s per-call deadline.
- `ross/store.py` — ClickHouse schema + `vector_search` (regime-scoped).
- `ross/server.py` — API: `/api/stream` (SSE), `/api/cite` + `/api/cites`
  (citation resolver w/ verified/web trust tiers), `/api/graph` (corpus map),
  `/api/replay`.
- `ross/corpus/` — scrapers: `healthcare.py` (USC via LII + CFR via eCFR),
  `oig.py` (advisory opinion PDFs), `ingest.py` (chunk → embed → ClickHouse).
- `web/src/app/page.tsx` — landing + workspace. `corpus/page.tsx` — the graph.

## Corpus (shared, in Cloud)
~1,900 federal authorities: statutes + CFR sections + 441 OIG advisory opinions,
across Stark / AKS / FCA / HIPAA / EMTALA / CMP / Part 2 / Insurance-&-Payer.
You only touch the scrapers if you're **expanding** the corpus:
```bash
uv run python -m ross.corpus.healthcare   # statutes + regs
uv run python -m ross.corpus.oig          # OIG opinions
uv run python -m ross.corpus.ingest       # re-embed + load (TRUNCATES + reloads)
```
⚠️ `ingest` truncates the shared tables and reloads from `data/raw/*.jsonl` —
coordinate before running it against Cloud.

## Conventions
- No tests, no ORMs, no agent frameworks. Talk to ClickHouse + OpenRouter directly.
- Every legal claim the Drafter makes carries an inline `[Cite: ...]`; the UI
  resolves each to verified (corpus) / web (fetched) / unverified.
- Never fabricate a citation — flag `[needs verification]` instead.
