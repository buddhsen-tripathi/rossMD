"""The orchestrator. Hand-written, no framework — the dance IS the product.

Flow (dynamic, not rigid):
  Intake → Issue Spotter → Researchers (fan-out, parallel, each does retrieval)
  → Strategist → Adversary → Drafter ⇄ Harvey (capped critique loop) → done.

Every step emits an event (consumed by the live theater + persisted to traces).
The whole blackboard is persisted to `runs` at the end.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import date
from typing import Awaitable, Callable

from ross import store
from ross.agents import prompts
from ross.corpus.ingest import CHUNK_COLS, DOC_COLS, split
from ross.embed import embed, embed_one
from ross.llm import LLM
from ross.trace import emit_dd, flush_dd
from ross.web import web_fetch

Emit = Callable[[dict], Awaitable[None]]
HARVEY_MAX_ROUNDS = 4
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
    def _fmt_authorities(chunks: list[dict], web: list[dict] | None = None) -> str:
        out = []
        for c in chunks:
            out.append(f"[CORPUS doc_id={c['doc_id']}] {c['title']} — {c['citation']}\n"
                       f"  {c['text'][:900]}")
        for w in (web or []):
            out.append(f"[LIVE WEB — UNVERIFIED doc_id={w['doc_id']}] {w['title']} — {w['url']}\n"
                       f"  {(w.get('text') or '')[:900]}")
        if not out:
            return "(no authorities retrieved — corpus thin on this issue)"
        return "\n\n".join(out)

    # ── web-search autonomy ───────────────────────────────────────────
    async def route(self, issue: dict, corpus_hits: list[dict]) -> dict:
        """Decide where this issue's authority lives: clickhouse | web | both |
        human_needed — and why. A first-class agent decision, not a fallback."""
        preview = "; ".join(f"{c['title']} ({c['citation']})" for c in corpus_hits[:6]) \
            or "(corpus returned nothing for this issue)"
        user = json.dumps({
            "issue": {k: issue.get(k) for k in ("label", "area", "theory", "authorities_to_find")},
            "corpus_preview": preview})
        dec = await self.llm.complete_json(
            agent="researcher", system=prompts.RETRIEVAL_ROUTER, user=user, max_tokens=800)
        if dec.get("decision") not in ("clickhouse", "web", "both", "human_needed"):
            dec["decision"] = "clickhouse"
        return dec

    def _cache_web_source(self, src: dict, area: str) -> dict:
        """Persist a fetched web source into ClickHouse (documents + embedded
        chunks) so it enters the SAME retrieval / citation / graph / replay path
        as the corpus. Tagged source='web' so it stays Tier-2/unverified."""
        url = src.get("url", "")
        doc_id = "web-" + hashlib.sha1(url.encode()).hexdigest()[:16]
        title = src.get("title") or url
        kind = src.get("kind", "payer_policy")
        text = src.get("text", "")
        try:
            c = store.client()
            if not c.query("SELECT 1 FROM documents WHERE doc_id=%(d)s LIMIT 1",
                           parameters={"d": doc_id}).result_rows:
                # always tag a practice area so the node clusters in the graph
                # (payer policies default to the insurance/payer regime)
                c.insert("documents",
                         [[doc_id, "web", kind, "", title, title, "", None, url, text, [],
                           [area or "insurance"]]],
                         column_names=DOC_COLS)
                passages = split(text)[:12]
                if passages:
                    vecs = embed([f"{title}\n{p}" for p in passages])
                    rows = [[f"{doc_id}-{i}", doc_id, i, kind, title, title, url, p, v]
                            for i, (p, v) in enumerate(zip(passages, vecs))]
                    c.insert("chunks", rows, column_names=CHUNK_COLS,
                             settings={"allow_experimental_vector_similarity_index": 1})
        except Exception:
            pass  # caching is best-effort; the source still feeds this run
        return {"doc_id": doc_id, "title": title, "citation": title,
                "url": url, "kind": kind, "text": text}

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
        iid = issue["id"]
        await self._event("researcher", "start", {"issue_id": iid, "label": issue["label"]})
        chunks = self.retrieve(issue)

        # decide where this issue's authority lives (first-class, not a fallback)
        route = await self.route(issue, chunks)
        decision, reason = route["decision"], route.get("reason", "")
        await self._event("researcher", "route",
                          {"issue_id": iid, "decision": decision, "reason": reason,
                           "queries": route.get("web_queries", [])})

        # live web retrieval BEFORE drafting, when the agent asked for it
        web_auths: list[dict] = []
        if decision in ("web", "both"):
            for q in (route.get("web_queries") or [])[:2]:
                src = await asyncio.to_thread(web_fetch, q)   # off the event loop (render can be slow)
                if src:
                    web_auths.append(await asyncio.to_thread(
                        self._cache_web_source, src, issue.get("area", "")))
            await self._event("researcher", "web_search",
                              {"issue_id": iid, "n": len(web_auths),
                               "queries": route.get("web_queries", []),
                               "sources": [{"title": w["title"], "url": w["url"], "kind": w["kind"]}
                                           for w in web_auths]})
        elif decision == "human_needed":
            await self._event("researcher", "human_needed", {"issue_id": iid, "reason": reason})

        # corpus + web fold into ONE authority list (same provenance path)
        authorities = [{"doc_id": c["doc_id"], "title": c["title"], "citation": c["citation"],
                        "url": c["url"], "kind": "corpus"} for c in chunks] + \
                      [{"doc_id": w["doc_id"], "title": w["title"], "citation": w["citation"],
                        "url": w["url"], "kind": w["kind"]} for w in web_auths]
        await self._event("researcher", "retrieved",
                          {"issue_id": iid, "authorities": authorities})

        user = (f"ISSUE:\n{json.dumps(issue)}\n\n"
                f"RETRIEVED AUTHORITIES (corpus + live web):\n"
                f"{self._fmt_authorities(chunks, web_auths)}")
        note = await self.llm.complete_json(
            agent="researcher", system=prompts.RESEARCHER, user=user, max_tokens=5000)
        note["issue_id"] = iid
        await self._event("researcher", "done",
                          {"issue_id": iid, "bottom_line": note.get("bottom_line", "")})
        return note

    async def research_all(self, issues: list[dict]) -> list[dict]:
        return await asyncio.gather(*(self.research_one(i) for i in issues))

    async def fetch_cited_policy(self, facts: dict) -> dict | None:
        """Deterministic web search: if the denial cited a payer policy, fetch it
        live (it is NEVER in our corpus). Guarantees the web agent engages on a
        payer-refusal matter — independent of the per-issue router's judgment —
        and seeds the policy into ClickHouse so every researcher can retrieve it."""
        d = facts.get("denial") or {}
        policy = (d.get("policy_cited") or "").strip()
        if not policy:
            return None
        q = " ".join(x for x in [d.get("payer", ""), policy, d.get("service_denied", ""),
                                 "medical necessity coverage criteria"] if x)
        await self._event("researcher", "web_search",
                          {"cited_policy": True, "policy": policy, "queries": [q],
                           "status": "fetching", "n": 0})
        src = await asyncio.to_thread(web_fetch, q)
        if not src:
            await self._event("researcher", "web_search",
                              {"cited_policy": True, "policy": policy, "n": 0,
                               "note": "policy not retrievable live"})
            return None
        cached = await asyncio.to_thread(self._cache_web_source, src, "insurance")
        await self._event("researcher", "web_search",
                          {"cited_policy": True, "policy": policy, "n": 1,
                           "sources": [{"title": cached["title"], "url": cached["url"],
                                        "kind": cached["kind"]}]})
        return cached

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
                           "adversary": adversary, "harvey_fixes": harvey_fixes or [],
                           "today": date.today().isoformat()})
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
        # deterministic web search: pull the policy the denial cited (never in the
        # corpus) up front, so every researcher can retrieve it during fan-out
        bb["cited_policy"] = await self.fetch_cited_policy(bb["facts"])
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
        # refine the "what would tighten this" questions from the COMPLETE record
        bb["open_questions"] = await self.open_questions(bb)

        await self._persist(run_id, scenario, bb)
        await self._event("orchestrator", "run_done", {"run_id": run_id})
        await self.llm.aclose()
        await flush_dd()  # make sure observability posts land before we return
        return bb

    async def open_questions(self, bb: dict) -> list[str]:
        """Post-analysis: the highest-leverage facts/documents still needed,
        synthesized from the WHOLE record (not just intake's first guesses)."""
        await self._event("orchestrator", "open_questions_start", {})
        user = json.dumps({
            "intake_missing": (bb.get("facts") or {}).get("missing_facts", []),
            "denial": (bb.get("facts") or {}).get("denial"),
            "issues": [i.get("label") for i in bb.get("issues", [])],
            "research_gaps": [{"issue": r.get("issue_id"), "bottom_line": r.get("bottom_line"),
                               "against_us": r.get("against_us")} for r in bb.get("research", [])],
            "adversary_attacks": (bb.get("adversary") or {}).get("attacks"),
            "harvey_fixes": (bb.get("harvey") or {}).get("fixes"),
            "posture": (bb.get("theory") or {}).get("posture"),
        })
        res = await self.llm.complete_json(
            agent="orchestrator", system=prompts.OPEN_QUESTIONS, user=user, max_tokens=1200)
        qs = [q for q in res.get("open_questions", []) if isinstance(q, str)][:5]
        await self._event("orchestrator", "open_questions", {"questions": qs})
        return qs

    async def _persist(self, run_id, scenario, bb):
        try:
            store.client().insert(
                "runs", [[run_id, scenario, "done", json.dumps(bb)]],
                column_names=["run_id", "scenario", "status", "blackboard"])
        except Exception as e:
            await self._event("orchestrator", "persist_error", {"error": str(e)})
