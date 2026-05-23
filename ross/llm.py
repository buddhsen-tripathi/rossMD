"""OpenRouter client (OpenAI-compatible). Every agent brain routes here.

Thin async wrapper over the chat-completions endpoint with retry, JSON-mode
helper, and a per-call trace hook the orchestrator uses to stream events.
"""
import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import (DEEP_EFFORT, MODEL_DEEP, MODEL_FAST,
                         OPENROUTER_API_KEY, OPENROUTER_BASE_URL)

TraceHook = Callable[[dict], Awaitable[None]]

# Hard ceiling per LLM call. Gemini-via-OpenRouter occasionally returns a
# degenerate trickle response (finish=None, no content) that never completes;
# httpx's read-timeout never fires because bytes keep arriving. asyncio.wait_for
# is the only thing that reliably kills it. Abort fast, retry once.
CALL_DEADLINE_S = 30


class LLM:
    def __init__(self, on_event: Optional[TraceHook] = None):
        self.on_event = on_event
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://ross.local",
                "X-Title": "Ross - The Pre-Lawyer",
            },
            timeout=httpx.Timeout(CALL_DEADLINE_S, connect=10),
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _post(self, payload: dict) -> dict:
        # wall-clock cap that survives slow-trickle responses
        async with asyncio.timeout(CALL_DEADLINE_S):
            r = await self._client.post("/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()

    async def complete(
        self,
        *,
        agent: str,
        system: str,
        user: str,
        strong: bool = False,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> str:
        model = MODEL_DEEP if strong else MODEL_FAST
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Thinkers reason (medium); workers run with thinking OFF for speed.
        # Flash supports disabling thinking; Pro ignores `enabled:false` (min budget).
        effort = reasoning_effort or (DEEP_EFFORT if strong else "none")
        if effort == "none":
            payload["reasoning"] = {"enabled": False}
        elif effort != "default":
            payload["reasoning"] = {"effort": effort}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # Gemini occasionally returns null content (reasoning ate the budget) or a
        # degenerate trickle that times out. Retry once with lighter reasoning; on
        # ultimate failure, degrade to empty so the run continues (don't crash).
        text, usage = "", {}
        for attempt in range(2):  # one retry max — bounds worst-case latency
            try:
                data = await self._post(payload)
            except Exception:
                payload["reasoning"] = {"effort": "low"}
                continue
            msg = data["choices"][0].get("message", {})
            text = msg.get("content") or ""
            usage = data.get("usage", {})
            if text.strip():
                break
            payload["max_tokens"] = min(int(payload["max_tokens"] * 1.5), 16000)
            payload["reasoning"] = {"effort": "low"}

        if self.on_event:
            await self.on_event({
                "type": "llm_call",
                "agent": agent,
                "model": model,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            })
        return text

    async def complete_json(self, **kw) -> dict:
        """Same as complete() but parses JSON. complete() already retries empty
        content internally, so parse once here (repair on truncation) — no extra
        model calls, to keep latency bounded."""
        raw = await self.complete(json_mode=True, **kw)
        try:
            return _parse_json(raw)
        except json.JSONDecodeError:
            return _parse_json_repair(raw)

    async def aclose(self):
        await self._client.aclose()


def _parse_json(raw: str) -> dict:
    s = (raw or "").strip()
    if not s:
        return {}
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # last-ditch: grab outermost braces
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            return json.loads(s[a:b + 1])
        raise


def _parse_json_repair(raw: str) -> dict:
    """Best-effort repair of truncated JSON (close open strings/brackets)."""
    s = (raw or "").strip()
    a = s.find("{")
    if a == -1:
        return {}
    s = s[a:]
    # close an unterminated string, then balance braces/brackets
    if s.count('"') % 2:
        s += '"'
    stack = []
    for ch in s:
        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    s = s.rstrip().rstrip(",")
    for opener in reversed(stack):
        s += "}" if opener == "{" else "]"
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}
