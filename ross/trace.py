"""Datadog observability for the agent system.

Per agent event we send, fire-and-forget (never blocks the run):
  • a structured LOG (run / agent / event / tokens / verdict / posture) — the
    audit stream you can filter by run or agent in Datadog Logs;
  • METRICS — `ross.llm.tokens` (gauge, by agent/model) and `ross.agent.activity`
    (count, by agent/event) — so a dashboard can graph token usage and the
    multi-agent flow.

Pure no-op when DD_API_KEY is unset. Uses the HTTP intake APIs directly.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from ross.config import DD_API_KEY, DD_SITE

_client = httpx.AsyncClient(timeout=5) if DD_API_KEY else None
_LOGS = f"https://http-intake.logs.{DD_SITE}/api/v2/logs"
_SERIES = f"https://api.{DD_SITE}/api/v1/series"
_HEADERS = {"DD-API-KEY": DD_API_KEY, "Content-Type": "application/json"}
_pending: set = set()


async def _send(run_id: str, ev: dict):
    payload = ev.get("payload", {})
    agent, event = ev.get("agent"), ev.get("event")
    log = {
        "ddsource": "ross", "service": "ross-agents",
        "ddtags": f"run:{run_id},agent:{agent},event:{event}",
        "message": f"{agent}/{event}",
        "agent": agent, "event": event, "seq": ev.get("seq"),
        **{k: payload[k] for k in ("model", "prompt_tokens", "completion_tokens",
                                   "verdict", "posture", "error") if k in payload},
    }
    now = time.time()
    metrics = [{
        "metric": "ross.agent.activity", "type": "count",
        "points": [[now, 1]],
        "tags": [f"agent:{agent}", f"event:{event}", f"run:{run_id}"],
    }]
    if payload.get("completion_tokens"):
        metrics.append({
            "metric": "ross.llm.tokens", "type": "gauge",
            "points": [[now, payload["completion_tokens"]]],
            "tags": [f"agent:{agent}", f"model:{payload.get('model', '')}"],
        })
    try:
        await asyncio.gather(
            _client.post(_LOGS, headers=_HEADERS, json=[log]),
            _client.post(_SERIES, headers=_HEADERS, json={"series": metrics}),
            return_exceptions=True,
        )
    except Exception:
        pass  # observability must never break the run


async def emit_dd(run_id: str, ev: dict):
    if not DD_API_KEY:
        return
    t = asyncio.create_task(_send(run_id, ev))  # fire-and-forget — zero latency
    _pending.add(t)
    t.add_done_callback(_pending.discard)


async def flush_dd():
    """Await any in-flight Datadog posts (so short-lived runs don't drop them)."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
