"""Datadog observability for the agent system.

Sends one log/metric per agent event to Datadog (latency, tokens, verdicts,
errors). Pure no-op when DD_API_KEY is unset, so the system runs fine without
it. Uses the HTTP intake API directly — no agent install needed.
"""
from __future__ import annotations

import time

import httpx

from ross.config import DD_API_KEY, DD_SITE

_client = httpx.AsyncClient(timeout=5) if DD_API_KEY else None
_t0 = time.time()


async def emit_dd(run_id: str, ev: dict):
    if not DD_API_KEY:
        return
    payload = ev.get("payload", {})
    log = {
        "ddsource": "ross",
        "service": "ross-agents",
        "ddtags": f"run:{run_id},agent:{ev.get('agent')},event:{ev.get('event')}",
        "message": f"{ev.get('agent')}/{ev.get('event')}",
        "agent": ev.get("agent"),
        "event": ev.get("event"),
        "seq": ev.get("seq"),
        "elapsed_s": round(time.time() - _t0, 2),
        **{k: payload[k] for k in ("model", "prompt_tokens", "completion_tokens",
                                   "verdict", "posture", "error") if k in payload},
    }
    try:
        await _client.post(
            f"https://http-intake.logs.{DD_SITE}/api/v2/logs",
            headers={"DD-API-KEY": DD_API_KEY, "Content-Type": "application/json"},
            json=[log],
        )
    except Exception:
        pass  # observability must never break the run
