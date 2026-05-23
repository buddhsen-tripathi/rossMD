"""Tier-2 web fetch via Nimble — live primary-source lookup when the corpus misses.

Two-step, restricted to AUTHORITATIVE domains so a "fetched" citation still
points at a real statute / regulation / opinion / case, not a blog:
  1) Nimble SERP search (Google), scoped with site: filters,
  2) Nimble Web API renders the top authoritative hit, then we extract text.
Results are flagged unverified (Tier 2) — the trust hierarchy stays explicit.
No-op without a key.
"""
import re

import httpx

from ross.config import NIMBLE_API_KEY

# only primary-source / government / court domains
AUTHORITATIVE = [
    "ecfr.gov", "law.cornell.edu", "oig.hhs.gov", "courtlistener.com",
    "govinfo.gov", "cms.gov", "hhs.gov", "federalregister.gov",
    "dol.gov", "uscode.house.gov", "supremecourt.gov", "medicaid.gov",
]

# payers' own clinical-policy sources — current coverage criteria the corpus
# can't hold (the policy a denial cites). Fetched but tagged distinctly so a
# "payer policy" never masquerades as primary government authority.
PAYER_POLICY = [
    "aetna.com", "uhcprovider.com", "uhc.com", "unitedhealthcare.com",
    "cigna.com", "anthem.com", "bcbs.com", "humana.com",
    "mcg.com", "changehealthcare.com",  # InterQual
]

ALLOWED = AUTHORITATIVE + PAYER_POLICY


def _kind(url: str) -> str:
    """Provenance tag for a fetched URL."""
    return "payer_policy" if any(d in url for d in PAYER_POLICY) else "primary"


SERP_URL = "https://api.webit.live/api/v1/realtime/serp"
WEB_URL = "https://api.webit.live/api/v1/realtime/web"


def _headers() -> dict:
    return {"Authorization": f"Bearer {NIMBLE_API_KEY}",
            "Content-Type": "application/json"}


def _serp_top(query: str, domains: list[str]) -> dict | None:
    """Top organic result on one of `domains`, via Nimble SERP."""
    site_filter = " OR ".join(f"site:{d}" for d in domains)
    r = httpx.post(
        SERP_URL, headers=_headers(),
        json={"search_engine": "google_search", "country": "US",
              "locale": "en", "query": f"{query} ({site_filter})", "parse": True},
        timeout=30,
    )
    r.raise_for_status()
    organics = (((r.json().get("parsing") or {}).get("entities") or {})
                .get("OrganicResult") or [])
    for o in organics:
        url = o.get("url") or o.get("link") or ""
        if any(d in url for d in domains):
            return {"url": url, "title": o.get("title") or o.get("name") or ""}
    return None


def _render_text(url: str) -> str:
    """Fetch fully-rendered HTML through Nimble, then strip to readable text."""
    r = httpx.post(
        WEB_URL, headers=_headers(),
        json={"url": url, "method": "GET", "render": True, "country": "US",
              "locale": "en", "parse": False},
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    html = (data.get("html_content") or data.get("body")
            or (data.get("data") or {}).get("content") or "")
    if not html:
        return ""
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"&nbsp;", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def web_fetch(query: str, domains: list[str] | None = None) -> dict | None:
    """Top result with extracted text from an allowed domain (gov primary
    sources + payer-policy sites by default), tagged with provenance. Or None."""
    if not NIMBLE_API_KEY:
        return None
    try:
        hit = _serp_top(query, domains or ALLOWED)
        if not hit:
            return None
        text = _render_text(hit["url"])
    except Exception:
        return None
    if len(text) < 200:
        return None
    return {
        "title": hit["title"] or query,
        "url": hit["url"],
        "text": text[:12000],
        "kind": _kind(hit["url"]),
    }
