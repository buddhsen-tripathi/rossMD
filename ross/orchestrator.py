"""The orchestrator. Hand-written, no framework — the dance IS the product.

Flow (dynamic, not rigid):
  Intake → Issue Spotter → Researchers (fan-out, parallel, each does retrieval)
  → Strategist → Adversary → Drafter ⇄ Harvey (capped critique loop) → done.

Every step emits an event (consumed by the live theater + persisted to traces).
The whole blackboard is persisted to `runs` at the end.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Awaitable, Callable

from ross import store
from ross.agents import prompts
from ross.embed import embed_one
from ross.llm import LLM
from ross.trace import emit_dd, flush_dd

Emit = Callable[[dict], Awaitable[None]]
HARVEY_MAX_ROUNDS = 2
RESEARCH_K = 8

# issue area → document practice-area tags to scope retrieval to that regime.
# OIG guidance rides along with the fraud-and-abuse regimes that cite it.
_INSURANCE = ["insurance", "erisa", "aca", "nsa", "parity", "mlr",
              "medicare-advantage", "managed-care"]
REGIME_TAGS = {
    "stark": ["stark", "oig"], "aks": ["aks", "oig"], "fca": ["fca", "oig"],
    "cmp": ["cmp", "oig"], "exclusion": ["exclusion", "oig"],
    "hipaa": ["hipaa"], "emtala": ["emtala"], "part2": ["part2", "sud"],
    "insurance": _INSURANCE, "erisa": _INSURANCE,
}


def _parse_drafter(raw: str) -> dict:
    """Parse the drafter's markdown: `DOCTYPE: x` line, `# Title`, then body."""
    raw = (raw or "").strip()
    if raw.startswith("```"):  # strip stray fences
        raw = raw.strip("`")
        raw = raw[raw.find("\n") + 1:] if "\n" in raw else raw
    doc_type, title, lines = "memo", "", raw.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.upper().startswith("DOCTYPE:"):
            doc_type = line.split(":", 1)[1].strip() or "memo"
            body_start = i + 1
            break
    body_lines = lines[body_start:]
    for i, line in enumerate(body_lines):
        if line.startswith("# "):
            title = line[2:].strip()
            body_lines = body_lines[i + 1:]
            break
    body = "\n".join(body_lines).strip()
    if not title:  # fallback: first non-empty line
        title = next((l.strip("# ").strip() for l in body.splitlines() if l.strip()), "Work Product")
    return {
        "doc_type": doc_type,
        "title": title,
        "body_markdown": body or raw,
        "citations_used": sorted(set(re.findall(r"\[Cite:\s*([^\]]+)\]", raw))),
    }


class Orchestrator:
    def __init__(self, emit: Emit):
        self.emit = emit
        self._seq = 0
        self._run_id = ""
        self.llm = LLM(on_event=self._on_llm)

    async def _on_llm(self, ev: dict):
        await self._event(ev["agent"], "llm_call", ev)

    async def _event(self, agent: str, event: str, payload: dict):
        self._seq += 1
        ev = {"agent": agent, "event": event, "seq": self._seq, "payload": payload}
        # persist trace centrally so every run is replayable, regardless of caller
        try:
            store.client().insert(
                "traces",
                [[self._run_id, self._seq, agent, event, json.dumps(payload)]],
                column_names=["run_id", "seq", "agent", "event", "payload"])
        except Exception:
            pass
        await emit_dd(self._run_id, ev)
        await self.emit(ev)

    # ── retrieval ─────────────────────────────────────────────────────
    def retrieve(self, issue: dict) -> list[dict]:
        query = " ".join([issue.get("label", ""), issue.get("theory", ""),
                          *issue.get("authorities_to_find", [])])
        try:
            vec = embed_one(query)
        except Exception:
            return []
        tags = REGIME_TAGS.get((issue.get("area") or "").lower())
        if not tags:
            return store.vector_search(vec, k=RESEARCH_K)
        # regime-scoped first; top up with a global search if the regime is thin
        scoped = store.vector_search(vec, k=RESEARCH_K, areas=tags)
        if len(scoped) >= 4:
            return scoped
        seen, out = {r["chunk_id"] for r in scoped}, list(scoped)
        for r in store.vector_search(vec, k=RESEARCH_K):
            if r["chunk_id"] not in seen:
                out.append(r)
        return out[:RESEARCH_K]

    @staticmethod
    def _fmt_authorities(chunks: list[dict]) -> str:
        if not chunks:
            return "(no authorities retrieved — corpus thin on this issue)"
        out = []
        for c in chunks:
            out.append(f"[doc_id={c['doc_id']}] {c['title']} — {c['citation']}\n"
                       f"  {c['text'][:900]}")
        return "\n\n".join(out)

    # ── agents ────────────────────────────────────────────────────────
    async def intake(self, scenario: str) -> dict:
        await self._event("intake", "start", {})
        facts = await self.llm.complete_json(
            agent="intake", system=prompts.INTAKE, user=scenario, max_tokens=4096)
        await self._event("intake", "done", {"summary": facts.get("summary", ""),
                                              "missing": facts.get("missing_facts", [])})
        return facts

    async def spot_issues(self, facts: dict) -> list[dict]:
        await self._event("issue_spotter", "start", {})
        res = await self.llm.complete_json(
            agent="issue_spotter", system=prompts.ISSUE_SPOTTER,
            user=json.dumps(facts), strong=True, max_tokens=8000)
        issues = res.get("issues", [])
        await self._event("issue_spotter", "done",
                          {"issues": [{"id": i["id"], "label": i["label"],
                                       "area": i.get("area"), "strength": i.get("strength"),
                                       "safe_harbor": i.get("exception_or_safe_harbor"),
                                       "theory": i.get("theory")}
                                      for i in issues]})
        return issues

    async def research_one(self, issue: dict) -> dict:
        await self._event("researcher", "start", {"issue_id": issue["id"], "label": issue["label"]})
        chunks = self.retrieve(issue)
        await self._event("researcher", "retrieved",
                          {"issue_id": issue["id"],
                           "authorities": [{"doc_id": c["doc_id"], "title": c["title"],
                                            "citation": c["citation"], "url": c["url"]}
                                           for c in chunks]})
        user = (f"ISSUE:\n{json.dumps(issue)}\n\n"
                f"RETRIEVED NY AUTHORITIES:\n{self._fmt_authorities(chunks)}")
        note = await self.llm.complete_json(
            agent="researcher", system=prompts.RESEARCHER, user=user, max_tokens=5000)
        note["issue_id"] = issue["id"]
        await self._event("researcher", "done",
                          {"issue_id": issue["id"], "bottom_line": note.get("bottom_line", "")})
        return note

    async def research_all(self, issues: list[dict]) -> list[dict]:
        return await asyncio.gather(*(self.research_one(i) for i in issues))

    async def strategize(self, facts, issues, research) -> dict:
        await self._event("strategist", "start", {})
        user = json.dumps({"facts": facts, "issues": issues, "research": research})
        theory = await self.llm.complete_json(
            agent="strategist", system=prompts.STRATEGIST, user=user,
            strong=True, max_tokens=8000)
        await self._event("strategist", "done",
                          {"posture": theory.get("posture"),
                           "killer_move": theory.get("killer_move"),
                           "strategy": theory.get("strategy"),
                           "structure": [s.get("step") for s in theory.get("structure", [])
                                         if isinstance(s, dict)][:5]})
        return theory

    async def adversary(self, facts, issues, research) -> dict:
        await self._event("adversary", "start", {})
        # attacks the exposure (issues + research), not our exact theory — so it
        # can run concurrently with the Strategist
        user = json.dumps({"facts": facts, "issues": issues, "research": research})
        attacks = await self.llm.complete_json(
            agent="adversary", system=prompts.ADVERSARY, user=user,
            strong=True, temperature=0.6, max_tokens=8000)
        await self._event("adversary", "done",
                          {"weakest_link": attacks.get("weakest_link"),
                           "n_attacks": len(attacks.get("attacks", [])),
                           "attacks": attacks.get("attacks", [])[:6]})
        return attacks

    async def draft(self, facts, theory, research, adversary, harvey_fixes=None) -> dict:
        await self._event("drafter", "start", {"revision": bool(harvey_fixes)})
        user = json.dumps({"facts": facts, "theory": theory, "research": research,
                           "adversary": adversary, "harvey_fixes": harvey_fixes or []})
        # markdown out (not JSON) — long documents truncate badly inside JSON strings
        raw = await self.llm.complete(
            agent="drafter", system=prompts.DRAFTER, user=user, max_tokens=12000)
        doc = _parse_drafter(raw)
        await self._event("drafter", "done",
                          {"doc_type": doc["doc_type"], "title": doc["title"],
                           "body_markdown": doc["body_markdown"]})
        return doc

    async def harvey(self, facts, theory, adversary, draft, rnd) -> dict:
        await self._event("harvey", "start", {"round": rnd})
        user = json.dumps({"facts": facts, "theory": theory,
                           "adversary": adversary, "draft": draft})
        verdict = await self.llm.complete_json(
            agent="harvey", system=prompts.HARVEY, user=user,
            strong=True, temperature=0.5, max_tokens=6000)
        await self._event("harvey", "verdict",
                          {"verdict": verdict.get("verdict"),
                           "one_liner": verdict.get("one_liner"),
                           "fixes": verdict.get("fixes", []),
                           "assessment": verdict.get("assessment")})
        return verdict

    # ── run ───────────────────────────────────────────────────────────
    async def run(self, scenario: str) -> dict:
        run_id = uuid.uuid4().hex[:12]
        self._run_id = run_id
        await self._event("orchestrator", "run_start", {"run_id": run_id})
        bb: dict = {"run_id": run_id, "scenario": scenario}

        bb["facts"] = await self.intake(scenario)
        bb["issues"] = await self.spot_issues(bb["facts"])
        await self._event("orchestrator", "fan_out", {"n": len(bb["issues"])})
        bb["research"] = await self.research_all(bb["issues"])
        # Strategist (builds the theory) and Adversary (attacks the exposure) have
        # no dependency on each other — run them concurrently.
        bb["theory"], bb["adversary"] = await asyncio.gather(
            self.strategize(bb["facts"], bb["issues"], bb["research"]),
            self.adversary(bb["facts"], bb["issues"], bb["research"]),
        )

        draft = await self.draft(bb["facts"], bb["theory"], bb["research"], bb["adversary"])
        harvey = None
        for rnd in range(1, HARVEY_MAX_ROUNDS + 1):
            harvey = await self.harvey(bb["facts"], bb["theory"], bb["adversary"], draft, rnd)
            if harvey.get("verdict") == "approve":
                break
            await self._event("orchestrator", "harvey_reject", {"round": rnd})
            draft = await self.draft(bb["facts"], bb["theory"], bb["research"],
                                     bb["adversary"], harvey_fixes=harvey.get("fixes"))
        bb["draft"] = draft
        bb["harvey"] = harvey

        await self._persist(run_id, scenario, bb)
        await self._event("orchestrator", "run_done", {"run_id": run_id})
        await self.llm.aclose()
        await flush_dd()  # make sure observability posts land before we return
        return bb

    async def _persist(self, run_id, scenario, bb):
        try:
            store.client().insert(
                "runs", [[run_id, scenario, "done", json.dumps(bb)]],
                column_names=["run_id", "scenario", "status", "blackboard"])
        except Exception as e:
            await self._event("orchestrator", "persist_error", {"error": str(e)})
