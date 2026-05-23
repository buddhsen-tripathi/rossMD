"""Ross API: kick off a run, stream the agent theater over SSE, serve citations.

  GET  /api/stream?scenario=...   SSE feed of agent events (drives the UI)
  GET  /api/doc/{doc_id}          full source text for the citation layer
  GET  /api/runs/{run_id}         final blackboard
  GET  /api/replay/{run_id}       canned replay (demo safety net)
  GET  /api/health                creds/corpus status

Run:  uv run uvicorn ross.server:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ross import store
from ross.config import (CH, COURTLISTENER_TOKEN, DD_API_KEY, DD_SITE,
                         NIMBLE_API_KEY, OPENROUTER_API_KEY)
from ross.orchestrator import Orchestrator
from ross.web import web_fetch

app = FastAPI(title="Ross MD — Healthcare Regulatory")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (s or "").lower())


def source_url(doc_type: str, citation: str, stored: str) -> str:
    """A human-browsable, working source link. Cases → CourtListener citation
    redirect (falls back to Google Scholar); statutes → official/stored URL."""
    if doc_type != "case":
        return stored or f"https://scholar.google.com/scholar?q={quote(citation)}"
    m = re.match(r"^\s*(\d+)\s+(.+?)\s+(\d+)\s*$", citation or "")
    if m:
        vol, rep, page = m.group(1), m.group(2).strip(), m.group(3)
        return f"https://www.courtlistener.com/c/{quote(rep)}/{vol}/{page}/"
    return f"https://scholar.google.com/scholar?q={quote(citation)}"


@app.get("/api/health")
def health():
    return {
        "openrouter": bool(OPENROUTER_API_KEY),
        "clickhouse": bool(CH["host"]),
        "courtlistener": bool(COURTLISTENER_TOKEN),
        "nimble": bool(NIMBLE_API_KEY),
        "datadog": bool(DD_API_KEY),
        "dd_site": DD_SITE if DD_API_KEY else "",
    }


@app.get("/api/stream")
async def stream(scenario: str):
    """Run Ross and stream every agent event as it happens."""
    queue: asyncio.Queue = asyncio.Queue()
    seq_holder = {"run_id": None}

    async def emit(ev: dict):
        # trace persistence happens inside the orchestrator now; server just relays
        if ev.get("event") == "run_start":
            seq_holder["run_id"] = ev["payload"].get("run_id")
        await queue.put(ev)

    async def driver():
        try:
            await Orchestrator(emit).run(scenario)
        except Exception as e:
            await queue.put({"agent": "orchestrator", "event": "error",
                             "payload": {"error": str(e)}})
        finally:
            await queue.put(None)  # sentinel

    async def gen():
        task = asyncio.create_task(driver())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield _sse(ev)
        finally:
            task.cancel()
        yield _sse({"agent": "orchestrator", "event": "stream_end", "payload": {}})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


REGIME = {
    "stark": "Stark Law", "aks": "Anti-Kickback", "fca": "False Claims Act",
    "qui tam": "False Claims Act", "hipaa": "HIPAA", "emtala": "EMTALA",
    "cmp": "Civil Penalties", "exclusion": "Exclusion", "part2": "42 CFR Part 2",
    "sud": "42 CFR Part 2", "oig": "OIG Guidance",
    # insurance / payer
    "insurance": "Insurance & Payer", "erisa": "Insurance & Payer",
    "aca": "Insurance & Payer", "nsa": "Insurance & Payer",
    "parity": "Insurance & Payer", "mlr": "Insurance & Payer",
    "medicare-advantage": "Insurance & Payer", "managed-care": "Insurance & Payer",
}


_USC_REF = re.compile(r"(\d+)\s+U\.?\s?S\.?\s?C\.?\s+(?:§+\s*)?(\d+[a-z0-9\-]*)", re.I)
_CFR_REF = re.compile(r"(\d+)\s+C\.?\s?F\.?\s?R\.?\s+(?:§+\s*)?(\d+\.\d+)", re.I)
_BARE_CFR = re.compile(r"§+\s*(\d+\.\d+)")
_USC_THIS = re.compile(r"section\s+(\d+[a-z0-9\-]*)\s+of\s+this\s+title", re.I)
_OIG_REF = re.compile(r"Advisory Opinion No\.?\s+(\d{2}-\d{2})", re.I)
_SSA_REF = re.compile(r"section\s+(1877|1128B|1128A|1128)\b", re.I)
# Social Security Act section → its U.S. Code home (what OIG opinions cite)
_SSA_USC = {"1877": "usc-42-1395nn", "1128b": "usc-42-1320a-7b",
            "1128a": "usc-42-1320a-7a", "1128": "usc-42-1320a-7"}


def _xrefs(doc_id: str, text: str, docids: set) -> set:
    """Cross-references from this doc's text to other corpus authorities."""
    own_title = doc_id.split("-")[1] if "-" in doc_id else ""
    out = set()
    t = text or ""
    for ti, sec in _USC_REF.findall(t):
        out.add(f"usc-{ti}-{sec.lower()}")
    for ti, sec in _CFR_REF.findall(t):
        out.add(f"cfr-{ti}-{sec}")
    if doc_id.startswith("cfr-"):
        for sec in _BARE_CFR.findall(t):
            out.add(f"cfr-{own_title}-{sec}")
    if doc_id.startswith("usc-"):
        for sec in _USC_THIS.findall(t):
            out.add(f"usc-{own_title}-{sec.lower()}")
    # OIG opinions: cite each other + the statutes by SSA section number
    for num in _OIG_REF.findall(t):
        out.add(f"oig-{num}")
    for ssa in _SSA_REF.findall(t):
        out.add(_SSA_USC[ssa.lower()])
    return {d for d in out if d in docids and d != doc_id}


@app.get("/api/graph")
def graph():
    """The corpus as a regulatory map. Authorities cluster into their regime
    (Stark, AKS, FCA, HIPAA, …) AND link to each other by their REAL
    cross-references (a Stark exception reg → the Stark statute; regs citing
    regs; OIG opinions → the safe harbors they interpret)."""
    c = store.client()
    rows = c.query(
        "SELECT doc_id, citation, title, doc_type, practice_area, text FROM documents"
    ).result_rows
    docids = {r[0] for r in rows}

    nodes, links, hub_deg, xdeg = [], [], {}, {}
    for doc_id, cite, title, dtype, areas, text in rows:
        nodes.append({"id": doc_id, "cite": cite, "title": title,
                      "type": dtype, "regime": "", "deg": 1})
        # regime hub (clustering + label). OIG opinions form their own cluster;
        # their links into AKS/Stark come through the real cross-references.
        regimes = ["OIG Guidance"] if doc_id.startswith("oig-") else [
            REGIME[a] for a in (areas or []) if a in REGIME]
        seen = set()
        for hub in regimes:
            if hub not in seen:
                seen.add(hub)
                links.append({"source": doc_id, "target": f"hub:{hub}", "kind": "regime"})
                hub_deg[hub] = hub_deg.get(hub, 0) + 1
        if seen:
            nodes[-1]["regime"] = next(iter(seen))
        # real cross-references (correlation)
        for tgt in _xrefs(doc_id, text, docids):
            links.append({"source": doc_id, "target": tgt, "kind": "xref"})
            xdeg[tgt] = xdeg.get(tgt, 0) + 1

    for n in nodes:
        n["deg"] = xdeg.get(n["id"], 0)  # in-degree = how many authorities cite it
    for hub, deg in hub_deg.items():
        nodes.append({"id": f"hub:{hub}", "cite": hub, "title": hub,
                      "type": "regime", "regime": hub, "deg": deg})

    n_xref = sum(1 for l in links if l["kind"] == "xref")
    st = c.query("""
        SELECT (SELECT count() FROM documents),
               (SELECT count() FROM chunks),
               (SELECT countIf(doc_type='statute') FROM documents),
               (SELECT countIf(doc_type='regulation') FROM documents)
    """).result_rows[0]
    return {
        "stats": {"docs": st[0], "chunks": st[1], "statutes": st[2],
                  "regulations": st[3], "regimes": len(hub_deg), "cross_refs": n_xref},
        "nodes": nodes, "links": links,
    }


@app.get("/api/last-run")
def last_run():
    """Most recent run_id — powers the one-click demo replay."""
    res = store.client().query(
        "SELECT run_id, scenario FROM runs ORDER BY created_at DESC LIMIT 1")
    if not res.result_rows:
        return {"run_id": None}
    return {"run_id": res.result_rows[0][0], "scenario": res.result_rows[0][1]}


def _doc_row(row: dict) -> dict:
    row["found"] = True
    # cached live-web sources stay Tier-2/unverified even though they live in the
    # documents table — a payer policy never masquerades as primary authority.
    is_web = row.get("source") == "web"
    row["tier"] = "web" if is_web else "corpus"
    row["verified"] = not is_web
    row["source_url"] = (row.get("url") or "") if is_web else source_url(
        row.get("doc_type", ""), row.get("citation", ""), row.get("url", ""))
    return row


@app.get("/api/doc/{doc_id}")
def get_doc(doc_id: str):
    res = store.client().query(
        "SELECT doc_id, doc_type, title, citation, court, url, text, source "
        "FROM documents WHERE doc_id = %(d)s LIMIT 1", parameters={"d": doc_id})
    if not res.result_rows:
        return {"found": False, "doc_id": doc_id}
    return _doc_row(dict(zip(res.column_names, res.result_rows[0])))


_SELECT = ("SELECT doc_id, doc_type, title, citation, court, url, text, source, "
           "lower(replaceRegexpAll(citation,'[^0-9a-zA-Z]','')) AS k FROM documents")


def _hit(res):
    if not res.result_rows:
        return None
    row = dict(zip(res.column_names, res.result_rows[0]))
    row.pop("k", None)
    return _doc_row(row)


# NY reporter-aware citation extractor (handles N.Y.2d, A.D.3d, Misc. 3d, …)
_REPORTER = r"(?:N\.?\s?Y\.?\s?S?\.?|A\.?\s?D\.?|App\.?\s?(?:Div|Term)\.?|Misc\.?|N\.?\s?E\.?)\s?(?:[23]d)?"
_CITE_RE = re.compile(rf"(\d+)\s+({_REPORTER})\s+(\d+)")


@app.get("/api/cite")
def get_cite(q: str):
    """Resolve one citation against the corpus; web-fetch on miss (Tier 2)."""
    return _resolve(q, allow_web=True)


@app.post("/api/cites")
def get_cites(payload: dict):
    """Batch corpus-only resolution for the work-product tally (one request,
    no per-cite fan-out, no web fetch). Returns {cite: {tier, found}}."""
    out = {}
    for q in payload.get("queries", [])[:80]:
        try:
            r = _resolve(q, allow_web=False)
            out[q] = {"tier": r.get("tier", "none"), "found": r.get("found", False)}
        except Exception:
            out[q] = {"tier": "none", "found": False}
    return out


def _resolve(q: str, allow_web: bool = True) -> dict:
    """Resolve a raw inline citation against the FULL corpus. Matches the
    extracted reporter citation / OIG number / CFR-USC section EXACTLY (no loose
    substring → no false hits). Web-fetches authoritative domains on miss when
    allow_web is set."""
    c = store.client()
    # 0) OIG advisory opinion — match by the YY-NN number → oig- doc_id
    if re.search(r"adv|opinion|\bAO\b", q, re.I):
        om = re.search(r"\b(\d{2})-(\d{2})\b", q)
        if om:
            hit = _hit(c.query(f"{_SELECT} WHERE doc_id = %(d)s LIMIT 1",
                               parameters={"d": f"oig-{om.group(1)}-{om.group(2)}"}))
            if hit:
                return hit

    m = _CITE_RE.search(q)
    cite_token = f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else q
    qn = _norm(q)

    # 1) exact match on the extracted reporter citation (cases)
    if m:
        key = _norm(f"{m.group(1)}{m.group(2)}{m.group(3)}")
        hit = _hit(c.query(f"{_SELECT} WHERE k = %(k)s LIMIT 1", parameters={"k": key}))
        if hit:
            return hit
    # 2) exact match on the whole normalized string
    hit = _hit(c.query(f"{_SELECT} WHERE k = %(k)s LIMIT 1", parameters={"k": qn}))
    if hit:
        return hit
    # 3) statute subsection: stored citation is a prefix of the query (§296 ⊂ §296(7))
    if not m and len(qn) >= 8:
        hit = _hit(c.query(
            f"{_SELECT} WHERE doc_type != 'case' AND length(k) >= 8 "
            f"AND position(%(qn)s, k) > 0 ORDER BY length(k) DESC LIMIT 1",
            parameters={"qn": qn}))
        if hit:
            return hit
    # corpus miss → Tier 2: live fetch from authoritative domains, flagged unverified
    web = web_fetch(q) if allow_web else None
    if web:
        return {
            "found": True, "tier": "web", "verified": False,
            "title": web["title"], "citation": cite_token,
            "text": web["text"], "source_url": web["url"],
        }
    # nothing — honest, with a working lookup link for the real citation
    is_statute = bool(re.search(r"§|law|code", q, re.I)) and not m
    return {
        "found": False, "tier": "none", "citation": cite_token,
        "source_url": source_url("statute" if is_statute else "case", cite_token, ""),
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    res = store.client().query(
        "SELECT blackboard FROM runs WHERE run_id = %(r)s LIMIT 1",
        parameters={"r": run_id})
    if not res.result_rows:
        return {"found": False}
    return json.loads(res.result_rows[0][0])


@app.get("/api/replay/{run_id}")
async def replay(run_id: str, speed: float = 1.0):
    """Replay a recorded run's trace feed — animates the theater with zero LLM calls."""
    res = store.client().query(
        "SELECT seq, agent, event, payload FROM traces "
        "WHERE run_id = %(r)s ORDER BY seq ASC", parameters={"r": run_id})
    rows = [dict(zip(res.column_names, r)) for r in res.result_rows]

    async def gen():
        for r in rows:
            r["payload"] = json.loads(r["payload"]) if r["payload"] else {}
            yield _sse(r)
            await asyncio.sleep(0.35 / max(speed, 0.1))
        yield _sse({"agent": "orchestrator", "event": "stream_end", "payload": {}})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
