.PHONY: ch-up ch-down db scrape-healthcare scrape-oig scrape-oig-guidance scrape-all ingest rebuild api web bringup

# 0. local ClickHouse (no creds, no signup) — or point .env at ClickHouse Cloud
ch-up:
	docker compose up -d
	@echo "ClickHouse on :8123 (user=default pass=ross_local)"

ch-down:
	docker compose down

# 1. create ClickHouse schema (+ HNSW vector index)
db:
	uv run python -m ross.store

# 2. corpus scrapers — federal healthcare law (no keys needed)
scrape-healthcare:        # USC statutes (LII) + CFR regs (eCFR) incl. insurance/payer
	uv run python -m ross.corpus.healthcare
scrape-oig:               # HHS OIG advisory opinions 1997–present (PDF)
	uv run python -m ross.corpus.oig
scrape-oig-guidance:      # Special Fraud Alerts, Advisory Bulletins, Compliance Guidance
	uv run python -m ross.corpus.oig_guidance
scrape-all: scrape-healthcare scrape-oig scrape-oig-guidance

# 3. embed into ClickHouse. Default = INCREMENTAL: only new docs are embedded +
# appended; the live corpus is never truncated (safe to run mid-demo).
ingest:
	uv run python -m ross.corpus.ingest

# atomic full re-embed: load to staging, then EXCHANGE TABLES (zero downtime)
rebuild:
	uv run python -m ross.corpus.ingest --rebuild

# 4. backend API (SSE agent theater) / frontend
api:
	uv run uvicorn ross.server:app --reload --port 8000
web:
	npm --prefix web run dev

# corpus foundation in one shot (local ClickHouse)
bringup: ch-up db scrape-all ingest
	@echo "✓ corpus seeded. now: make api   (and in another shell) make web"
