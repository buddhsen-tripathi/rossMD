"""Tier-2 web fetch via Exa — live primary-source lookup when the corpus misses.

Restricted to AUTHORITATIVE domains so a "fetched" citation still points at a
real statute / regulation / opinion / case, not a blog. Results are flagged
unverified (Tier 2) — the trust hierarchy stays explicit. No-op without a key.
"""
import httpx

from ross.config import EXA_API_KEY

# only primary-source / government / court domains
AUTHORITATIVE = [
    "ecfr.gov", "law.cornell.edu", "oig.hhs.gov", "courtlistener.com",
    "govinfo.gov", "cms.gov", "hhs.gov", "federalregister.gov",
    "dol.gov", "uscode.house.gov", "supremecourt.gov", "medicaid.gov",
]


def exa_fetch(query: str) -> dict | None:
    """Top authoritative-domain result with extracted text, or None."""
    if not EXA_API_KEY:
        return None
    try:
        r = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
            json={
                "query": query,
                "type": "auto",
                "numResults": 1,
                "includeDomains": AUTHORITATIVE,
                "contents": {"text": {"maxCharacters": 12000}},
            },
            timeout=20,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception:
        return None
    if not results:
        return None
    top = results[0]
    text = (top.get("text") or "").strip()
    if len(text) < 200:
        return None
    return {"title": top.get("title") or query, "url": top.get("url", ""), "text": text}
