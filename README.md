# Ross MD — Healthcare Regulatory Associate

A multi-agent **healthcare regulatory legal team** in software. Drop in a real
situation — a physician compensation arrangement, a HIPAA breach, an OIG
subpoena — and Ross spins up a seven-agent pipeline that issue-spots the
fraud-and-abuse exposure, researches it against a corpus of primary authority,
builds a strategy, war-games the government's attack, and drafts the actual
work product (a compliance memo, an arrangement-structuring memo, an OIG
advisory-opinion request, a CID/subpoena response, a breach response, or a
defense outline) — cited, supervised, and streamed live in ~90 seconds.

The reader is assumed to be a **healthcare lawyer** — outside counsel, a
hospital GC, or a compliance officer — so the output is attorney work product,
not consumer advice. It spans the full regulatory lifecycle: *advise and
structure (compliance) → defend when the government comes (enforcement)*.

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
| **Intake** | Reads the file — parties, money flow, referrals, open questions. |
| **Issue Spotter** | Names every angle of regulatory exposure (Stark + AKS + FCA travel together). |
| **Researchers** | One per issue, fanned out in parallel; each retrieves authorities from the corpus and writes a research note. |
| **Strategist** | Builds one coherent compliance/defense theory and posture. |
| **Adversary** | Role-plays the government (DOJ Civil Fraud, AUSA, a relator's counsel, a State AG Medicaid Fraud Control Unit, a payer SIU) and pre-empts its best attacks. |
| **Drafter** | Produces the work product the posture calls for. |
| **Harvey** | The unforgiving supervising partner — reviews the draft and sends it back for revision until it earns an approval (capped rounds). |

Every step emits an event, consumed live by the UI **and** persisted to a
ClickHouse audit trail. The Strategist and Adversary run concurrently (no
dependency between them); the Drafter ⇄ Harvey revision loop runs until Harvey
approves or the round cap is hit.

## What's in the corpus

Federal healthcare fraud-and-abuse and compliance law, plus case law:

- **Fraud & abuse:** Stark Law (§1395nn), Anti-Kickback Statute (§1320a-7b),
  False Claims Act / qui tam (31 U.S.C. §§3729–3733), civil monetary penalties,
  exclusions.
- **Privacy & care:** HIPAA (Privacy/Security/Breach — 45 CFR 160/162/164),
  EMTALA, 42 CFR Part 2 (SUD records).
- **Sub-regulatory gold:** HHS OIG advisory opinions (1997–present) and the
  AKS safe harbors / Stark exceptions they interpret (42 CFR Part 1001, 411).
- **Payer / insurance:** ERISA, ACA market reforms, No Surprises Act, mental-health parity.
- **Case law:** NY opinions from the open Caselaw Access Project (+ optional CourtListener).

The corpus is also exposed as a **regulatory map** (`/api/graph`): authorities
cluster by regime (Stark, AKS, FCA, HIPAA…) and link by their *real*
cross-references — a Stark exception reg → the Stark statute; OIG opinions →
the safe harbors they cite.

## Stack

- **OpenRouter** — every agent brain (Gemini Pro for the thinkers, Flash for the workers).
- **ClickHouse** — one store, four jobs: corpus + vector index + agent blackboard + audit trail.
- **fastembed / BGE-small** — local 384-dim embeddings (no API).
- **Nimble** — gov-site scraping for verbatim statute text **and** the Tier-2 live web fetch (SERP search + render, restricted to authoritative primary-source domains) when a cite misses the corpus.
- **CourtListener** — supplementary NY case law (free token).
- **Datadog** — traces every agent event (no-op without a key).
- **Next.js** — the dark, dense "Agent Theater" UI.

## Setup

The only credential you actually need is **`OPENROUTER_API_KEY`** (the agent
brains). ClickHouse runs locally in Docker — no signup. Case law comes from the
open Caselaw Access Project — no token.

```bash
cp .env.example .env        # add OPENROUTER_API_KEY; defaults point at local ClickHouse
make bringup                # ch-up → db → scrape (CAP) → ingest (embed locally)
make api                    # backend (FastAPI + SSE) on :8000
make web                    # frontend on :3000
```

`.env` defaults already point at the local Docker ClickHouse (`localhost:8123`,
user `default`, pass `ross_local`). Optional keys: `NIMBLE_API_KEY` (verbatim
statute text + Tier-2 web fetch), `COURTLISTENER_TOKEN` (case-law full text),
`DD_API_KEY` (observability). To use ClickHouse Cloud instead, swap
`CLICKHOUSE_HOST/PORT/PASSWORD` and set `CLICKHOUSE_SECURE=true`.

### Make targets

| Target | What it does |
|--------|--------------|
| `make ch-up` / `ch-down` | Start / stop local ClickHouse (Docker). |
| `make db` | Create the ClickHouse schema. |
| `make scrape` / `scrape-big` | Pull NY case law from CAP (citation graph, no key). |
| `make scrape-cl` | Supplementary CourtListener metadata (needs token for full text). |
| `make statutes` | Backfill verbatim statute text via Nimble (seed already loaded). |
| `make ingest` | Embed every `data/raw/*.jsonl` doc into ClickHouse. |
| `make api` / `make web` | Run the backend / frontend. |
| `make bringup` | `ch-up → db → scrape → ingest` in one shot. |

### Try it headless

`uv run python run_demo.py` runs the full pipeline on a built-in Stark/AKS
medical-director scenario and prints the live trace, Harvey's verdict, and the
draft head to stdout — the fastest way to see the agents work without the UI.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/stream?scenario=…` | SSE feed of every agent event (drives the live theater). |
| `GET /api/health` | Creds / corpus status. |
| `GET /api/graph` | The corpus as a regulatory map (regime clusters + cross-references). |
| `GET /api/doc/{doc_id}` | Full source text for the citation layer. |
| `GET /api/cite` · `POST /api/cites` | Resolve a citation (corpus hit → Tier-2 web fetch → honest miss). |
| `GET /api/runs/{run_id}` | Final blackboard for a run. |
| `GET /api/last-run` | Most recent run's id. |
| `GET /api/replay/{run_id}` | Canned replay with zero LLM calls (demo safety net). |

## Layout

```
ross/
  config.py           env / model routing
  store.py            ClickHouse schema + vector_search
  embed.py            local BGE embeddings
  llm.py              OpenRouter client (traced)
  orchestrator.py     the agent dance (hand-written, no framework)
  web.py              Tier-2 live web fetch via Nimble (SERP + render)
  trace.py            Datadog
  server.py           FastAPI: /api/stream (SSE), /api/graph, /api/doc, /api/replay, …
  agents/prompts.py   the seven agent personalities  ← the product
  corpus/
    caselaw.py        NY case law from the Caselaw Access Project
    courtlistener.py  supplementary NY case law
    healthcare.py     federal healthcare statutes + regulations (eCFR / Cornell LII)
    statutes.py       verbatim statute text via Nimble
    oig.py            HHS OIG advisory opinions
    ingest.py         JSONL → chunks → embeddings → ClickHouse
data/                 scraped + seeded JSONL (bulk caselaw corpus is gitignored)
web/                  Next.js Agent Theater
  src/app/page.tsx        the live theater (agent activity feed + work product)
  src/app/corpus/page.tsx the regulatory map explorer
  src/components/         CitationDrawer (the citation layer)
  src/lib/ross.ts         SSE client + run-state reducer
```

## Demo safety

Every live run persists its trace to ClickHouse `traces`. Replay any run with
zero LLM calls via `GET /api/replay/{run_id}` (the UI animates identically).
Pre-warm one rehearsed scenario and keep its `run_id` as a fallback.
