.PHONY: ch-up ch-down db scrape scrape-big scrape-cl statutes ingest api web bringup demo

# 0. local ClickHouse (no creds, no signup) — or point .env at ClickHouse Cloud
ch-up:
	docker compose up -d
	@echo "ClickHouse on :8123 (user=default pass=ross_local)"

ch-down:
	docker compose down

# 1. create ClickHouse schema (needs CLICKHOUSE_* in .env)
db:
	uv run python -m ross.store

# 2. scrape NY case law — CAP (full text + citation graph, NO key needed)
scrape:
	uv run python -m ross.corpus.caselaw

# bigger CAP sweep (more volumes / cases)
scrape-big:
	uv run python -m ross.corpus.caselaw --sweep

# supplementary: CourtListener metadata (needs COURTLISTENER_TOKEN for full text)
scrape-cl:
	uv run python -m ross.corpus.courtlistener

# 3. backfill verbatim statute text (needs NIMBLE_API_KEY; seed already loaded)
statutes:
	uv run python -m ross.corpus.statutes

# 4. embed everything in data/raw/*.jsonl into ClickHouse
ingest:
	uv run python -m ross.corpus.ingest

# 5. backend API (SSE agent theater)
api:
	uv run uvicorn ross.server:app --reload --port 8000

# 6. frontend
web:
	npm --prefix web run dev

# corpus foundation in one shot (local ClickHouse)
bringup: ch-up db scrape ingest
	@echo "✓ corpus seeded. now: make api   (and in another shell) make web"
