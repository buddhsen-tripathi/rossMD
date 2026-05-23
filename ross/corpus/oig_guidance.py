"""HHS OIG sub-regulatory guidance — Special Fraud Alerts, Advisory Bulletins,
and Compliance Program Guidance. These state the agency's enforcement
priorities (speaker programs, lab payments, PODs, telemarketing, MA marketing)
— exactly what counsel cites. Scraped from the OIG compliance pages (PDF/HTML).

Run:  uv run python -m ross.corpus.oig_guidance
"""
import asyncio
import io
import json
import re
import sys
from urllib.parse import unquote

import httpx
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import DATA_RAW

OUT = DATA_RAW / "oig_guidance.jsonl"
BASE = "https://oig.hhs.gov"
UA = {"User-Agent": "Mozilla/5.0 (ross-md/0.1)"}
INDEX_PAGES = [
    "/compliance/alerts/",
    "/compliance/compliance-guidance/",
    "/exclusions/special-advisory-bulletin-and-other-guidance/",
]
TYPE_LABEL = {
    "special-fraud-alerts": "Special Fraud Alert",
    "special-advisory-bulletins": "Special Advisory Bulletin",
    "compliance-guidance": "Compliance Program Guidance",
}
_DOC_RE = re.compile(
    r'<a[^>]*href="(/documents/([a-z-]+)/(\d+)/[^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def _get(client, url):
    return await client.get(url, timeout=60)


def _clean(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _extract(content: bytes, url: str) -> str:
    if url.lower().endswith(".pdf"):
        try:
            r = PdfReader(io.BytesIO(content))
            return "\n".join(p.extract_text() or "" for p in r.pages).strip()
        except Exception:
            return ""
    return _clean(content.decode("utf-8", "ignore"))


async def run():
    seen, docs = set(), []
    async with httpx.AsyncClient(headers=UA, follow_redirects=True) as client:
        # 1) gather guidance doc links from the index pages
        targets = []
        for page in INDEX_PAGES:
            try:
                html = (await _get(client, BASE + page)).text
            except Exception:
                continue
            for href, kind, did, text in _DOC_RE.findall(html):
                if kind not in TYPE_LABEL or did in seen:
                    continue
                seen.add(did)
                title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
                if not title:
                    title = unquote(href.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("_", " ")
                targets.append((href, kind, did, title[:160]))
        print(f"found {len(targets)} guidance docs")

        # 2) fetch + extract each
        sem = asyncio.Semaphore(6)
        f = OUT.open("w")

        async def grab(href, kind, did, title):
            async with sem:
                try:
                    text = _extract((await _get(client, BASE + href)).content, href)
                except Exception:
                    return
            if len(text) < 300:
                return
            label = TYPE_LABEL[kind]
            docs.append(1)
            rec = {
                "doc_id": f"oig-g-{did}", "source": "oig", "doc_type": "guidance",
                "jurisdiction": "US", "title": f"OIG {label}: {title}",
                "citation": f"OIG {label} — {title}",
                "url": BASE + href, "practice_area": ["aks", "oig"], "cites": [],
                "text": text,
            }
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"  ✓ {label}: {title[:60]} ({len(text)} chars)", flush=True)

        await asyncio.gather(*(grab(*t) for t in targets))
        f.close()
    print(f"✓ {len(docs)} OIG guidance docs → {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
