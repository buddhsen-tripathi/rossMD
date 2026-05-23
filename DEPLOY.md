# Deploying Ross MD

Two app services run behind a reverse proxy on one public origin:

| Path     | Service | What it is                        |
|----------|---------|-----------------------------------|
| `/api/*` | `api`   | FastAPI + the agent orchestrator  |
| `/*`     | `web`   | Next.js Agent Theater             |

The browser calls the API **same-origin** at `/api/*` — no separate API host,
no CORS. ClickHouse is **external** (ClickHouse Cloud); the app reads from it at
runtime and does not self-ingest.

## Prerequisite: seed ClickHouse Cloud (one time)

Point a local `.env` at your ClickHouse Cloud cluster and load the corpus once:

```bash
cp .env.example .env       # set CLICKHOUSE_* (SECURE=true) + OPENROUTER_API_KEY
make db                    # create schema
make scrape                # pull NY case law (CAP)
make ingest                # embed + load into ClickHouse Cloud
# optional: make statutes   (needs NIMBLE_API_KEY for verbatim statute text)
```

---

## Option A — docker-compose (recommended; e.g. a DigitalOcean Droplet)

Self-contained: `api` + `web` + a Caddy reverse proxy that routes `/api/*` to
the backend (prefix preserved) and everything else to the frontend. Runs on any
Docker host.

```bash
# on the host (a DO Droplet with Docker installed):
git clone https://github.com/buddhsen-tripathi/rossMD.git && cd rossMD
cp .env.example .env        # fill in the real keys + CLICKHOUSE_* (the Cloud cluster)
docker compose -f docker-compose.prod.yml up -d --build
```

- **HTTP only (IP / local):** leave `SITE_ADDRESS` unset → Caddy serves on `:80`.
- **HTTPS (domain):** point a DNS A record at the Droplet, set
  `SITE_ADDRESS=ross.example.com` in `.env`, and Caddy auto-provisions and
  renews TLS. Open ports 80 and 443.

Verify: `curl http://<host>/api/health` (JSON) and `curl http://<host>/` (HTML).

> Verified locally end-to-end: `/` serves the Next.js app and `/api/health`
> returns the FastAPI JSON, all through Caddy on one origin.

---

## Option B — DigitalOcean App Platform (PaaS, no VM to manage)

App Platform does **not** run docker-compose — it builds the Dockerfiles from a
spec. Use `.do/app.yaml` (two services: `api` at `/api` with the path prefix
preserved, `web` at `/`).

```bash
doctl apps create --spec .do/app.yaml
# updates:
doctl apps update <APP_ID> --spec .do/app.yaml
```

Set secrets (`OPENROUTER_API_KEY`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`, and
optional `NIMBLE_API_KEY` / `COURTLISTENER_TOKEN` / `DD_API_KEY`) in the
dashboard or via doctl — `.do/app.yaml` leaves them blank on purpose.
`deploy_on_push: true` redeploys on every push to `main`.

> Note: a single-service deploy (just the root `Dockerfile`) will 404 on `/`
> because FastAPI only serves `/api/*` — you need **both** components, which is
> why the spec defines two services.

---

## Notes (both options)

- **First boot** of `api` is slower — it loads the BGE embedding model. The
  model is baked into the image at build time (no runtime download).
- **SSE:** the live agent feed (`/api/stream`) streams over Server-Sent Events;
  the server sends `X-Accel-Buffering: no` and Caddy streams it through.
- **`docker-compose.yml`** (no `.prod`) remains the local-dev ClickHouse only.
