# Ross MD — Healthcare Regulatory Associate

A multi-agent **healthcare regulatory legal team** in software. Drop in a real
situation — a payer **denial letter**, a physician compensation arrangement, a
HIPAA breach, an OIG subpoena, an EMTALA notice — and Ross spins up a
seven-agent pipeline that issue-spots the exposure, researches it against a
corpus of primary authority, builds a strategy, war-games the government's (or
payer's) attack, and drafts the actual work product — cited, supervised, and
streamed live in ~90 seconds.

Two jobs, one team:

- **Refusal Rescue** — a payer (Aetna, UnitedHealthcare, an ERISA self-funded
  plan) refuses a claim "not medically necessary" or "experimental." Ross reads
  the denial, pulls the member's appeal rights (ERISA §1132, ACA external
  review, the No Surprises Act) and the payer's own policy, and builds a cited
  **appeal packet** that reverses it.
- **Fraud & abuse** — advise and structure an arrangement to fit a safe harbor,
  or defend it when the government comes (CID/subpoena, qui tam, OIG).

The reader is assumed to be a **healthcare lawyer** — outside counsel, a
hospital GC, or a compliance officer — so the output is attorney work product,
not consumer advice. It spans the full regulatory lifecycle: *advise and
structure (compliance) → win the appeal / defend the enforcement action*.

## The agent pipeline

```
Intake ─▶ Issue Spotter ─▶ Researchers (fan-out, parallel) ─┐
                                                            ├─▶ Strategist ─┐
                                                            └─▶ Adversary ──┤
                                                                            ▼
                                                  Drafter ⇄ Harvey (revise until approved)
```

| Agent | Role |
|-------|------|
| **Intake** | Reads the file — parties, money flow, referrals, the denial, open questions. |
| **Issue Spotter** | Names every angle of exposure (Stark + AKS + FCA travel together; ERISA + ACA + NSA for payer denials). |
| **Researchers** | One per issue, fanned out in parallel. Each first searches the corpus, then **routes**: stay corpus-only, reach for a **live web source** (the payer's clinical policy, a CMS manual) via Nimble, or **flag the issue for counsel** if it needs a human fact. Writes a research note. |
| **Strategist** | Builds one coherent compliance/appeal/defense theory and posture. |
| **Adversary** | Role-plays the other side (DOJ Civil Fraud, an AUSA, a relator's counsel, a State AG Medicaid Fraud Control Unit, a payer's SIU) and pre-empts its best attacks. |
| **Drafter** | Produces the work product the posture calls for — an appeal packet, a compliance/structuring memo, an OIG advisory-opinion request, a CID/subpoena response, a HIPAA breach response, or a defense outline. |
| **Harvey** | The unforgiving supervising partner — reviews the draft and sends it back for revision until it earns an approval (capped at 4 rounds). |

Every step emits an event, consumed live by the UI **and** persisted to a
ClickHouse audit trail. The Strategist and Adversary run **concurrently** (no
dependency between them); the Drafter ⇄ Harvey revision loop runs until Harvey
approves or the round cap is hit. Hand-written orchestrator — no agent framework.

## What's in the corpus

Federal healthcare fraud-and-abuse, payer/coverage, and privacy law, plus case
law — **~1,900 authorities / ~15,900 embedded passages / ~4,400 real
cross-references** today, and growing:

- **Fraud & abuse:** Stark Law (§1395nn), Anti-Kickback Statute (§1320a-7b),
  False Claims Act / qui tam (31 U.S.C. §§3729–3733), civil monetary penalties,
  exclusions.
- **Privacy & care:** HIPAA (Privacy/Security/Breach — 45 CFR 160/162/164),
  EMTALA, 42 CFR Part 2 (SUD records).
- **Payer / insurance:** ERISA (§1132 enforcement, §1144 preemption), ACA market
  reforms (42 U.S.C. §300gg), the No Surprises Act, mental-health parity,
  Medicare Advantage / Part D, Medicaid managed care.
- **Sub-regulatory gold:** HHS OIG advisory opinions (1997–present), Special
  Fraud Alerts and Compliance Guidance, and the AKS safe harbors / Stark
  exceptions they interpret (42 CFR Part 1001, 411).
- **Case law:** NY opinions from the open Caselaw Access Project (+ optional CourtListener).

The corpus is also exposed as a **regulatory map** (`/api/graph`): authorities
cluster by regime (Stark, AKS, FCA, HIPAA, EMTALA…) and link by their *real*
cross-references — a Stark exception reg → the Stark statute; OIG opinions → the
safe harbors they cite.

### ClickHouse as the agent's legal memory

One store does four jobs (surfaced live on the `/corpus` page):

| Job | What it is |
|-----|-----------|
| **Vector retrieval** | ~15,900 embedded passages, 384-dim, HNSW index for semantic search. |
| **Authority graph** | ~4,400 cross-references parsed from citation text — the citation network. |
| **Source cache** | Tier-2 live-web sources (payer policies, CMS manuals) cached as they're fetched. |
| **Replayable trace** | Every agent event of every run, persisted — fully replayable with zero LLM calls. |

## Stack

- **OpenRouter** — every agent brain. Default is **Gemini 2.5 Flash** for all
  seven agents (reasoning effort dialed up for the deep ones); set
  `ROSS_MODEL_DEEP=google/gemini-2.5-pro` to upgrade the thinkers.
- **ClickHouse** — one store, four jobs (above). Runs on **ClickHouse Cloud**
  (the team's shared store) or locally in Docker.
- **fastembed / BGE-small** — local 384-dim embeddings (no API).
- **Nimble** — gov-site scraping for verbatim statute text **and** the Tier-2
  live web fetch (SERP search + render, restricted to authoritative
  primary-source domains) the researchers route to when a cite misses the corpus.
- **CourtListener** — supplementary NY case law (free token).
- **Datadog** — traces every agent event (no-op without a key); also surfaced in
  the in-app **Observability** tab.
- **Next.js** — the dense **Agent Theater** UI, with a dark/light theme toggle
  (dark by default; choice persists; `?theme=light` URL override).

## Setup

The only credential you truly need is **`OPENROUTER_API_KEY`** (the agent
brains). The store defaults to **ClickHouse Cloud** — fill in the connection
creds — or run it locally in Docker (`make ch-up`).

```bash
cp .env.example .env        # add OPENROUTER_API_KEY + ClickHouse creds
make db                     # create the schema (+ HNSW vector index)
make scrape-all && make ingest   # build the corpus (embeds locally)
make api                    # backend (FastAPI + SSE) on :8000
make web                    # frontend on :3000
```

`.env.example` defaults to a **secure ClickHouse Cloud** connection
(`CLICKHOUSE_PORT=8443`, `CLICKHOUSE_SECURE=true`) — set `CLICKHOUSE_HOST` /
`CLICKHOUSE_PASSWORD`. To run **local** instead: `make ch-up`, then set
`CLICKHOUSE_HOST=localhost`, `CLICKHOUSE_PORT=8123`, `CLICKHOUSE_SECURE=false`.
Optional keys: `NIMBLE_API_KEY` (verbatim statute text + Tier-2 web fetch),
`COURTLISTENER_TOKEN` (case-law full text), `DD_API_KEY` + `DD_SITE`
(observability).

### Make targets

| Target | What it does |
|--------|--------------|
| `make ch-up` / `ch-down` | Start / stop local ClickHouse (Docker). |
| `make db` | Create the ClickHouse schema (+ HNSW vector index). |
| `make scrape-healthcare` | Federal healthcare statutes (LII) + regulations (eCFR), incl. insurance/payer. |
| `make scrape-oig` | HHS OIG advisory opinions (1997–present). |
| `make scrape-oig-guidance` | OIG Special Fraud Alerts, Advisory Bulletins, Compliance Guidance. |
| `make scrape-all` | All of the above. |
| `make ingest` | Embed every `data/raw/*.jsonl` doc into ClickHouse (incremental — appends new, never truncates). |
| `make rebuild` | Re-embed the whole corpus into a staging table and atomically swap it in (zero downtime). |
| `make api` / `make web` | Run the backend / frontend. |
| `make bringup` | `ch-up → db → scrape-all → ingest` in one shot (local). |

### Try it headless

`uv run python run_demo.py` runs the full pipeline on a built-in scenario and
prints the live trace, Harvey's verdict, and the draft head to stdout — the
fastest way to see the agents work without the UI.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/stream?scenario=…` | SSE feed of every agent event (drives the live theater). |
| `GET /api/health` | Creds / corpus status. |
| `GET /api/graph` | The corpus as a regulatory map (regime clusters + cross-references). |
| `GET /api/memory` | ClickHouse "legal memory" counts — vector / graph / source cache / trace. |
| `GET /api/doc/{doc_id}` | Full source text for the citation layer. |
| `GET /api/cite` · `POST /api/cites` | Resolve a citation (corpus hit → Tier-2 web fetch → honest miss). |
| `GET /api/runs/{run_id}` | Final blackboard for a run. |
| `GET /api/last-run` | Most recent run's id (powers one-click replay). |
| `GET /api/replay/{run_id}` | Canned replay with zero LLM calls (demo safety net). |

## Layout

```
ross/
  config.py           env / model routing
  store.py            ClickHouse schema + vector_search (HNSW)
  embed.py            local BGE embeddings
  llm.py              OpenRouter client (traced)
  orchestrator.py     the agent dance (hand-written, no framework)
  web.py              Tier-2 live web fetch via Nimble (SERP + render)
  trace.py            Datadog
  server.py           FastAPI: /api/stream (SSE), /api/graph, /api/memory, /api/replay, …
  agents/prompts.py   the seven agent personalities  ← the product
  corpus/
    caselaw.py        NY case law from the Caselaw Access Project
    courtlistener.py  supplementary NY case law
    healthcare.py     federal healthcare statutes + regulations (eCFR / Cornell LII)
    statutes.py       verbatim statute text via Nimble
    oig.py            HHS OIG advisory opinions
    oig_guidance.py   OIG Special Fraud Alerts / Bulletins / Compliance Guidance
    ingest.py         JSONL → chunks → embeddings → ClickHouse (incremental + atomic rebuild)
data/                 scraped + seeded JSONL (bulk caselaw corpus is gitignored)
web/                  Next.js Agent Theater
  src/app/page.tsx          the live theater (agent activity feed + work product + adversary + observability)
  src/app/corpus/page.tsx   the regulatory map + ClickHouse legal-memory stats
  src/components/           CitationDrawer, RetrievalGraph, ThemeToggle
  src/lib/ross.ts           SSE client + run-state reducer
```

## Demo safety

Every live run persists its trace to ClickHouse `traces`. Replay any run with
zero LLM calls via `GET /api/replay/{run_id}` (the UI animates identically).
Pre-warm one rehearsed scenario and keep its `run_id` as a fallback —
`/?replay=last` auto-plays the most recent run.
