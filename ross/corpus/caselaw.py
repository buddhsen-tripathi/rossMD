"""NY case law from the Caselaw Access Project (static.case.law).

Fully open, no auth, full opinion text + citation graph (`cites_to`). Two modes:
  • targeted  — fetch landmark precedents directly by citation (demo-critical)
  • sweep     — pull NY reporters by volume for breadth (semantic retrieval)

Writes JSONL (documents schema) to data/raw/caselaw.jsonl for ingest.py.

Run:  uv run python -m ross.corpus.caselaw            # targeted + bounded sweep
      uv run python -m ross.corpus.caselaw --sweep    # bigger volume sweep
"""
import asyncio
import json
import re
import sys

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import DATA_RAW

BASE = "https://static.case.law"
OUT = DATA_RAW / "caselaw.jsonl"
CONCURRENCY = 8

# citation reporter -> CAP slug
REPORTER_SLUG = {
    "N.Y.3d": "ny3d", "N.Y.2d": "ny-2d", "N.Y.": "ny",
    "A.D.3d": "ad3d", "A.D.2d": "ad2d", "A.D.": "ad",
    "Misc.3d": "misc3d", "Misc.2d": "misc2d", "Misc.": "misc",
    "N.Y.S.": "nys",
    # federal authority binding NY
    "U.S.": "us", "F.3d": "f3d", "F.2d": "f2d",
    "F. Supp. 3d": "f-supp-3d", "F. Supp. 2d": "f-supp-2d", "F. Supp.": "f-supp",
}

# Landmark precedents that make Ross look brilliant on the demo scenarios.
LANDMARKS = [
    "47 N.Y.2d 316",   # Park West Mgmt v. Mitchell — warranty of habitability
    "93 N.Y.2d 382",   # BDO Seidman v. Hirshberg — non-compete reasonableness
    "61 N.Y.2d 458",   # Murphy v. American Home Products — at-will employment
    "82 N.Y.2d 342",   # Sabetay / Weiner line — employment contract
    "98 N.Y.2d 562",   # Forrest v. Jewish Guild for the Blind — NYSHRL standard
    "85 N.Y.2d 20",     # Oswego Laborers v. Marine Midland — GBL 349 elements
    "2 N.Y.3d 247",    # Stutman v. Chemical Bank — GBL 349 deception
]

# SCOTUS authority binding on NY that the agents routinely cite (by citation).
FED_LANDMARKS = [
    "411 U.S. 792",   # McDonnell Douglas v. Green — burden-shifting framework
    "450 U.S. 248",   # Texas Dept. of Community Affairs v. Burdine — burden of proof
    "548 U.S. 53",    # Burlington N. & Santa Fe Ry. v. White — retaliation standard
    "524 U.S. 775",   # Faragher v. Boca Raton — employer harassment liability
    "524 U.S. 742",   # Burlington Industries v. Ellerth — harassment liability
    "477 U.S. 57",    # Meritor Savings Bank v. Vinson — hostile work environment
]

# Reporters to sweep, newest series first (most relevant, modern law).
SWEEP = ["ny3d", "ny-2d", "ad3d", "misc3d"]


def slug_for(reporter: str) -> str | None:
    return REPORTER_SLUG.get(reporter.strip())


def parse_cite(cite: str) -> tuple[str, int, int] | None:
    """'47 N.Y.2d 316' -> ('ny2d', 47, 316)."""
    # volume = leading int, page = trailing int, reporter = middle (may contain "2d"/"3d")
    m = re.match(r"^\s*(\d+)\s+(.+?)\s+(\d+)\s*$", cite)
    if not m:
        return None
    vol, rep, page = m.group(1), m.group(2).strip(), m.group(3)
    slug = slug_for(rep)
    return (slug, int(vol), int(page)) if slug else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=15))
async def _get_json(client: httpx.AsyncClient, url: str):
    r = await client.get(url, timeout=40)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def to_doc(c: dict) -> dict:
    cb = c.get("casebody", {}) or {}
    opinions = cb.get("opinions", []) or []
    text = "\n\n".join(o.get("text", "") for o in opinions).strip()
    head = cb.get("head_matter", "") or ""
    full = (head + "\n\n" + text).strip()
    cites = c.get("citations", []) or []
    primary = next((x["cite"] for x in cites if x.get("type") == "official"),
                   cites[0]["cite"] if cites else "")
    edges = [e["cite"] for e in (c.get("cites_to") or []) if e.get("cite")]
    return {
        "source": "cap",
        "doc_type": "case",
        "jurisdiction": "NY",
        "doc_id": f"cap-{c.get('id')}",
        "title": c.get("name_abbreviation") or c.get("name") or "",
        "citation": primary,
        "court": (c.get("court") or {}).get("name", ""),
        "date_filed": c.get("decision_date"),
        "url": f"https://static.case.law/{c.get('file_name','')}",
        "cites": edges,
        "practice_area": [],
        "text": full,
    }


async def fetch_by_citation(client, cite: str) -> dict | None:
    parsed = parse_cite(cite)
    if not parsed:
        return None
    slug, vol, page = parsed
    # try the common file ordinals at this page
    for ordinal in ("01", "02", "03"):
        url = f"{BASE}/{slug}/{vol}/cases/{page:04d}-{ordinal}.json"
        c = await _get_json(client, url)
        if c:
            return to_doc(c)
    return None


async def sweep_reporter(client, slug: str, max_volumes: int, max_cases: int,
                         seen: set, write) -> int:
    vols = await _get_json(client, f"{BASE}/{slug}/VolumesMetadata.json")
    if not vols:
        print(f"  {slug}: no volumes", file=sys.stderr)
        return 0
    n = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    for v in vols[:max_volumes]:
        if n >= max_cases:
            break
        folder = v.get("volume_folder")
        metas = await _get_json(client, f"{BASE}/{slug}/{folder}/CasesMetadata.json")
        if not metas:
            continue

        async def grab(meta):
            nonlocal n
            if n >= max_cases:
                return
            fn = meta.get("file_name")
            cid = f"cap-{meta.get('id')}"
            if not fn or cid in seen:
                return
            async with sem:
                c = await _get_json(client, f"{BASE}/{slug}/{folder}/cases/{fn}.json")
            if not c:
                return
            doc = to_doc(c)
            if len(doc["text"]) < 400:
                return
            seen.add(cid)
            write(doc)
            n += 1

        await asyncio.gather(*(grab(m) for m in metas))
        print(f"  {slug} vol {folder}: total {n}", flush=True)
    return n


async def run(big: bool = False):
    seen: set = set()
    count = 0
    f = OUT.open("w")

    def write(doc):
        f.write(json.dumps(doc) + "\n")
        f.flush()

    async with httpx.AsyncClient(headers={"User-Agent": "ross-prelawyer/0.1"}) as client:
        # 1) landmarks by citation (NY + binding federal)
        print("→ landmarks")
        for cite, tags in [(c, ["landmark"]) for c in LANDMARKS] + \
                          [(c, ["landmark", "federal"]) for c in FED_LANDMARKS]:
            doc = await fetch_by_citation(client, cite)
            if doc:
                doc["practice_area"] = tags
                write(doc)
                count += 1
                seen.add(doc["doc_id"])
                print(f"  ✓ {cite}: {doc['title']} ({len(doc['text'])} chars)")
            else:
                print(f"  ✗ {cite}: not found in CAP", file=sys.stderr)

        # 2) breadth sweep
        max_vols = 25 if big else 6
        max_cases = 2000 if big else 350
        print(f"→ sweep (≤{max_vols} vols, ≤{max_cases} cases each)")
        for slug in SWEEP:
            count += await sweep_reporter(client, slug, max_vols, max_cases, seen, write)

    f.close()
    print(f"✓ {count} cases → {OUT}")


if __name__ == "__main__":
    asyncio.run(run(big="--sweep" in sys.argv))
