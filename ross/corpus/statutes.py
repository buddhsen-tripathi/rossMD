"""NY statute / admin-code / NYCRR scraper via Nimble (anti-bot rendering).

Government legal sites (Justia, NY Senate, amlegal) sit behind Cloudflare/JS
challenges — exactly Nimble's job. This fetches rendered HTML through Nimble,
extracts the statute body, and writes JSONL that ingest.py picks up. It also
backfills verbatim text into the curated seed records (matched by URL).

NOTE: verify the Nimble endpoint/auth shape against your account on first run
(uv run python -m ross.corpus.statutes --check). Endpoint set per Nimble Web API.

Run:  uv run python -m ross.corpus.statutes
"""
import asyncio
import json
import re
import sys

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import DATA_RAW, NIMBLE_API_KEY

NIMBLE_URL = "https://api.webit.live/api/v1/realtime/web"
OUT = DATA_RAW / "ny_statutes.jsonl"

# Demo-critical provisions to pull verbatim. (citation, heading, url, areas)
TARGETS = [
    ("N.Y. Labor Law § 740", "Whistleblower retaliation",
     "https://www.nysenate.gov/legislation/laws/LAB/740", ["employment"]),
    ("N.Y. Exec. Law § 296", "NY State Human Rights Law",
     "https://www.nysenate.gov/legislation/laws/EXC/296", ["employment"]),
    ("N.Y. Labor Law § 198", "Wage remedies; attorneys' fees",
     "https://www.nysenate.gov/legislation/laws/LAB/198", ["employment"]),
    ("N.Y. Gen. Oblig. Law § 7-103", "Security deposit held in trust",
     "https://www.nysenate.gov/legislation/laws/GOB/7-103", ["housing"]),
    ("N.Y. Gen. Oblig. Law § 7-108", "Returning security deposits",
     "https://www.nysenate.gov/legislation/laws/GOB/7-108", ["housing"]),
    ("N.Y. Gen. Bus. Law § 349", "Deceptive acts and practices",
     "https://www.nysenate.gov/legislation/laws/GBS/349", ["consumer"]),
    ("N.Y. Real Prop. Law § 235-b", "Warranty of habitability",
     "https://www.nysenate.gov/legislation/laws/RPP/235-B", ["housing"]),
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
async def nimble_fetch(client: httpx.AsyncClient, url: str) -> str:
    """Fetch fully-rendered HTML for a URL through Nimble."""
    r = await client.post(
        NIMBLE_URL,
        headers={"Authorization": f"Bearer {NIMBLE_API_KEY}",
                 "Content-Type": "application/json"},
        json={"url": url, "method": "GET", "render": True, "country": "US",
              "locale": "en", "parse": False},
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    # Nimble returns the page under html_content / body depending on plan.
    return (data.get("html_content") or data.get("body")
            or (data.get("data") or {}).get("content") or "")


def extract_text(html: str) -> str:
    """Pull readable statute text out of rendered HTML (NY Senate / generic)."""
    if not html:
        return ""
    m = re.search(r'<div[^>]*class="[^"]*c-block--text[^"]*".*?</div>', html, re.S)
    blob = m.group(0) if m else html
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", blob, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"&nbsp;", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


async def run():
    if not NIMBLE_API_KEY:
        print("⚠️  No NIMBLE_API_KEY — skipping. Seed metadata already covers demo "
              "statutes; this backfills verbatim text.", file=sys.stderr)
        return
    n = 0
    async with httpx.AsyncClient() as client, OUT.open("w") as f:
        for cite, heading, url, areas in TARGETS:
            try:
                html = await nimble_fetch(client, url)
                text = extract_text(html)
            except Exception as e:
                print(f"  fail {cite}: {e}", file=sys.stderr)
                continue
            if len(text) < 200:
                print(f"  thin {cite} ({len(text)} chars) — check Nimble parse", file=sys.stderr)
            rec = {
                "source": "nysenate", "doc_type": "statute", "jurisdiction": "NY",
                "title": f"{cite} — {heading}", "citation": cite, "url": url,
                "practice_area": areas, "cites": [], "text": text,
            }
            f.write(json.dumps(rec) + "\n")
            n += 1
            print(f"  ✓ {cite} ({len(text)} chars)", flush=True)
    print(f"✓ {n} statutes → {OUT}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        print("NIMBLE_API_KEY set:", bool(NIMBLE_API_KEY))
    else:
        asyncio.run(run())
