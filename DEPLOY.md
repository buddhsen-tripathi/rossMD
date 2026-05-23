# Deploying Ross MD to DigitalOcean App Platform

Two services run under one app domain. App Platform's ingress handles the path
routing and TLS — there's no reverse proxy to run.

| Path     | Service | What it is                        |
|----------|---------|-----------------------------------|
| `/api/*` | `api`   | FastAPI + the agent orchestrator  |
| `/*`     | `web`   | Next.js Agent Theater             |

The browser calls the API **same-origin** at `/api/*`, so there's no separate
API host and no CORS. ClickHouse is **external** (ClickHouse Cloud) — the app
reads from it at runtime and does not self-ingest.

> **The two-service spec matters.** A single-service deploy (just the root
> `Dockerfile`) 404s on `/`, because FastAPI only serves `/api/*`. Both
> components must exist — that's what `.do/app.yaml` defines.

## 1. Seed ClickHouse Cloud (one time, before first deploy)

```bash
cp .env.example .env       # set CLICKHOUSE_* (SECURE=true) + OPENROUTER_API_KEY
make db                    # create schema
make scrape                # pull NY case law (CAP)
make ingest                # embed + load into ClickHouse Cloud
# optional: make statutes   (needs NIMBLE_API_KEY for verbatim statute text)
```

## 2. Deploy from the spec

```bash
doctl apps create --spec .do/app.yaml
# subsequent updates:
doctl apps update <APP_ID> --spec .do/app.yaml
```

`.do/app.yaml` defines both services and routes (`api` at `/api` with the path
prefix preserved, `web` at `/`). `deploy_on_push: true` redeploys on every push
to `main`.

## 3. Set secrets

The spec leaves credentials blank on purpose. Set the real values as App-Level
env vars (dashboard → Settings → App-Level Environment Variables, or via
`doctl`):

- **Required:** `OPENROUTER_API_KEY`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`
- **Optional:** `NIMBLE_API_KEY` (statute scrape + Tier-2 web fetch),
  `COURTLISTENER_TOKEN`, `DD_API_KEY` / `DD_SITE`

## Notes

- **First boot** of `api` is slower — it loads the BGE embedding model. The
  model is baked into the image at build time (no runtime download), and the
  health check allows a 30s startup delay.
- **SSE:** the live agent feed (`/api/stream`) streams over Server-Sent Events;
  the server sends `X-Accel-Buffering: no` so App Platform's proxy doesn't
  buffer it.
- **`docker-compose.yml`** (in the repo root) is local-dev ClickHouse only —
  not used by App Platform.
