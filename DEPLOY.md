# Deploying Ross MD to DigitalOcean App Platform

Two services run under one app domain:

| Path     | Service | What it is                        |
|----------|---------|-----------------------------------|
| `/api/*` | `api`   | FastAPI + the agent orchestrator  |
| `/*`     | `web`   | Next.js Agent Theater             |

The browser calls the API **same-origin** at `/api/*`, so there's no separate
API hostname to configure and no CORS surprises. ClickHouse is **external**
(ClickHouse Cloud) — App Platform doesn't manage stateful ClickHouse.

## 1. Seed ClickHouse Cloud (one time, before first deploy)

The app reads from ClickHouse at runtime but does **not** ingest. Point a local
`.env` at your ClickHouse Cloud cluster and load the corpus once:

```bash
cp .env.example .env       # set CLICKHOUSE_* to your Cloud cluster, SECURE=true
make db                    # create schema
make scrape                # pull NY case law (CAP)
make ingest                # embed + load into ClickHouse Cloud
# optional: make statutes   (needs NIMBLE_API_KEY for verbatim statute text)
```

## 2. Set secrets

`.do/app.yaml` leaves credentials blank on purpose. Set the real values as
App-Level env vars (dashboard → Settings → App-Level Environment Variables, or
via `doctl`):

- **Required:** `OPENROUTER_API_KEY`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`
- **Optional:** `NIMBLE_API_KEY` (statute scrape + Tier-2 web fetch),
  `COURTLISTENER_TOKEN`, `DD_API_KEY` / `DD_SITE` (observability)

Non-secret ClickHouse settings (`PORT`, `USER`, `DATABASE`, `SECURE`) are
already in the spec — adjust if your cluster differs.

## 3. Deploy

```bash
doctl apps create --spec .do/app.yaml
# subsequent updates:
doctl apps update <APP_ID> --spec .do/app.yaml
```

`deploy_on_push: true` is set, so pushes to `main` redeploy automatically.

## Notes

- **First boot** is slower on the `api` service: it loads the BGE embedding
  model. The model is baked into the image at build time (no download at
  runtime), and the health check allows a 30s startup delay.
- **SSE:** the live agent feed (`/api/stream`) streams over Server-Sent Events;
  the server already sends `X-Accel-Buffering: no` so App Platform's proxy
  doesn't buffer it.
- **Instance sizes:** `api` is `basic-xs` (fastembed/onnxruntime want RAM),
  `web` is `basic-xxs`. Bump in the spec if needed.
- **Local production-style run:** `docker compose` here is still just the local
  ClickHouse for development; the Dockerfiles are what App Platform builds.
