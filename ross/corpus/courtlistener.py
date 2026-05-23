"""CourtListener NY case-law scraper.

Free API token (instant signup) unlocks clean JSON + full opinion text.
Strategy: search to enumerate clusters across NY courts x practice areas,
then pull full opinion text per cluster. Streams JSONL to data/raw/.

Run:  uv run python -m ross.corpus.courtlistener
"""
import asyncio
import json
import sys
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import COURTLISTENER_TOKEN, DATA_RAW

BASE = "https://www.courtlistener.com/api/rest/v4"
OUT = DATA_RAW / "courtlistener.jsonl"

# NY courts available on CourtListener (invalid ids just return empty).
COURTS = [
    "ny",          # Court of Appeals
    "nyappdiv",    # Appellate Division
    "nyappterm",   # Appellate Term
    "nysupct",     # Supreme Court (trial)
    "nycivct",     # NYC Civil Court (incl. Housing Part)
    "nyfamct",     # Family Court
    "nysurct",     # Surrogate's Court
    "nycountyct",
]

# Practice-area probes — each is a strong-signal query for an issue Ross covers.
QUERIES = [
    "warranty of habitability 235-b",
    "rent stabilization overcharge",
    "security deposit general obligations 7-103",
    "constructive eviction tenant",
    "whistleblower labor law 740 retaliation",
    "wrongful termination at-will employee",
    "non-compete restrictive covenant enforceability",
    "discrimination executive law 296",
    "breach of contract damages",
    "deceptive business practice GBL 349",
    "negligence premises liability",
    "child custody best interests",
    "spousal maintenance domestic relations",
    "defamation slander per se",
    "fraud misrepresentation reliance",
]

MAX_PER_PROBE = 25          # clusters per (court, query)
CONCURRENCY = 6
SLEEP_BETWEEN_PAGES = 0.3


def headers() -> dict:
    h = {"Accept": "application/json", "User-Agent": "ross-md/0.1"}
    if COURTLISTENER_TOKEN:
        h["Authorization"] = f"Token {COURTLISTENER_TOKEN}"
    return h


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30))
async def _get(client: httpx.AsyncClient, url: str, params=None) -> dict:
    r = await client.get(url, params=params, headers=headers(), timeout=40)
    if r.status_code == 429:
        time.sleep(5)
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


async def search_clusters(client, court: str, query: str) -> list[dict]:
    """Enumerate opinion clusters for one (court, query)."""
    out, url = [], f"{BASE}/search/"
    params = {"q": query, "court": court, "type": "o", "page_size": 20}
    while url and len(out) < MAX_PER_PROBE:
        data = await _get(client, url, params)
        params = None  # cursor URL carries its own params
        for r in data.get("results", []):
            out.append(r)
            if len(out) >= MAX_PER_PROBE:
                break
        url = data.get("next")
        await asyncio.sleep(SLEEP_BETWEEN_PAGES)
    return out


async def fetch_opinion_text(client, cluster_id: int) -> str:
    """Full opinion text for a cluster (needs token; else empty)."""
    if not COURTLISTENER_TOKEN:
        return ""
    try:
        data = await _get(client, f"{BASE}/opinions/", {"cluster": cluster_id})
    except Exception:
        return ""
    for op in data.get("results", []):
        for key in ("plain_text", "html_with_citations", "html", "html_lawbox", "xml_harvard"):
            if op.get(key):
                return op[key]
    return ""


def to_doc(res: dict, text: str) -> dict:
    return {
        "source": "courtlistener",
        "doc_type": "case",
        "jurisdiction": "NY",
        "cluster_id": res.get("cluster_id"),
        "case_name": res.get("caseName") or res.get("caseNameFull"),
        "court": res.get("court"),
        "court_id": res.get("court_id"),
        "date_filed": res.get("dateFiled"),
        "citations": res.get("citation") or [],
        "docket_number": res.get("docketNumber"),
        "judge": res.get("judge"),
        "url": "https://www.courtlistener.com" + (res.get("absolute_url") or ""),
        "snippet": (res.get("opinions") or [{}])[0].get("snippet", "") if res.get("opinions") else "",
        "text": text,
        "text_len": len(text or ""),
    }


async def run():
    if not COURTLISTENER_TOKEN:
        print("⚠️  No COURTLISTENER_TOKEN — pulling metadata+snippets only "
              "(no full opinion text). Add token to .env for full text.", file=sys.stderr)

    seen: set[int] = set()
    sem = asyncio.Semaphore(CONCURRENCY)
    n = 0
    async with httpx.AsyncClient(follow_redirects=True) as client, OUT.open("w") as f:
        for court in COURTS:
            for q in QUERIES:
                try:
                    results = await search_clusters(client, court, q)
                except Exception as e:
                    print(f"  search fail {court} «{q[:20]}»: {e}", file=sys.stderr)
                    continue

                async def handle(res):
                    nonlocal n
                    cid = res.get("cluster_id")
                    if not cid or cid in seen:
                        return
                    seen.add(cid)
                    async with sem:
                        text = await fetch_opinion_text(client, cid)
                    doc = to_doc(res, text)
                    f.write(json.dumps(doc) + "\n")
                    f.flush()
                    n += 1

                await asyncio.gather(*(handle(r) for r in results))
                print(f"[{court:11}] «{q[:32]:32}» +{len(results):3} → total docs {n}",
                      flush=True)
    print(f"✓ done — {n} unique docs → {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
