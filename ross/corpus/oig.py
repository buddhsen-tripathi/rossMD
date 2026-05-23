"""HHS OIG Advisory Opinions — the sub-regulatory gold.

These are the agency telling lawyers "this arrangement is OK / is a kickback."
Each opinion lives at /compliance/advisory-opinions/{YY-NN}/ and links to a PDF.
Enumerate by number, fetch the PDF, extract text. Writes data/raw/oig.jsonl.

Run:  uv run python -m ross.corpus.oig
"""
import asyncio
import io
import json
import re
import sys

import httpx
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import DATA_RAW

OUT = DATA_RAW / "oig.jsonl"
BASE = "https://oig.hhs.gov"
UA = {"User-Agent": "Mozilla/5.0 (ross-md/0.1)"}
YEARS = [97, 98, 99] + list(range(0, 27))   # 1997–2026 (OIG AOs began in 1997)
NUMS = range(1, 26)                          # up to 25 opinions/year
CONCURRENCY = 8


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def _get(client, url):
    return await client.get(url, timeout=40)


def tag_areas(text: str) -> list[str]:
    t = text.lower()
    areas = []
    if "kickback" in t or "1128b" in t or "1320a-7b" in t:
        areas.append("aks")
    if "self-referral" in t or "section 1877" in t or "stark" in t or "1395nn" in t:
        areas.append("stark")
    if "civil monetary" in t or "1128a" in t:
        areas.append("cmp")
    return areas or ["aks"]


async def fetch_one(client, yy: int, nn: int) -> dict | None:
    num = f"{yy:02d}-{nn:02d}"
    try:
        r = await _get(client, f"{BASE}/compliance/advisory-opinions/{num}/")
    except Exception:
        return None
    if r.status_code != 200:
        return None
    m = re.search(r'href="(/documents/advisory-opinions/[^"]+\.pdf)"', r.text)
    if not m:
        return None
    try:
        pr = await _get(client, BASE + m.group(1))
        reader = PdfReader(io.BytesIO(pr.content))
        text = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
    except Exception:
        return None
    if len(text) < 500:
        return None
    disp = ""
    d = re.search(r"\((Favorable|Unfavorable|Modified)\)", text)
    if d:
        disp = f" ({d.group(1)})"
    return {
        "doc_id": f"oig-{num}",
        "source": "oig", "doc_type": "guidance", "jurisdiction": "US",
        "title": f"OIG Advisory Opinion No. {num}{disp}",
        "citation": f"OIG Adv. Op. No. {num}",
        "url": f"{BASE}/compliance/advisory-opinions/{num}/",
        "practice_area": tag_areas(text) + ["oig"],
        "cites": [], "text": text,
    }


async def run():
    n = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    f = OUT.open("w")

    async def worker(yy, nn):
        nonlocal n
        async with sem:
            doc = await fetch_one(client, yy, nn)
        if doc:
            f.write(json.dumps(doc) + "\n")
            f.flush()
            n += 1
            print(f"  ✓ {doc['citation']}{'' if doc['title'].endswith(')') is False else ''} "
                  f"({len(doc['text'])} chars)", flush=True)

    async with httpx.AsyncClient(headers=UA, follow_redirects=True) as client:
        tasks = [worker(yy, nn) for yy in YEARS for nn in NUMS]
        await asyncio.gather(*tasks)
    f.close()
    print(f"✓ {n} OIG advisory opinions → {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
