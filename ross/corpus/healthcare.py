"""Ross MD corpus — federal healthcare statutes + regulations.

Statutes  : U.S. Code via Cornell LII (clean static HTML).
Regulations: eCFR API (structured XML, one call per CFR part → per-section docs).

All public, no keys. Writes data/raw/healthcare.jsonl in the documents schema.

Run:  uv run python -m ross.corpus.healthcare
"""
import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ross.config import DATA_RAW

OUT = DATA_RAW / "healthcare.jsonl"
ECFR = "https://www.ecfr.gov/api/versioner/v1"
LII = "https://www.law.cornell.edu/uscode/text"
UA = {"User-Agent": "Mozilla/5.0 (ross-md/0.1)"}

# (title, section, citation, heading, practice_area[])
USC = [
    (42, "1395nn", "42 U.S.C. § 1395nn", "Stark Law — limitation on certain physician referrals", ["stark"]),
    (42, "1320a-7b", "42 U.S.C. § 1320a-7b", "Anti-Kickback Statute — criminal penalties for acts involving Federal health care programs", ["aks"]),
    (42, "1320a-7a", "42 U.S.C. § 1320a-7a", "Civil monetary penalties", ["cmp"]),
    (42, "1320a-7", "42 U.S.C. § 1320a-7", "Exclusion of certain individuals and entities from Federal health care programs", ["exclusion"]),
    (31, "3729", "31 U.S.C. § 3729", "False Claims Act — false claims liability", ["fca"]),
    (31, "3730", "31 U.S.C. § 3730", "False Claims Act — civil actions for false claims (qui tam)", ["fca", "qui tam"]),
    (31, "3731", "31 U.S.C. § 3731", "False Claims Act — false claims procedure", ["fca"]),
    (31, "3732", "31 U.S.C. § 3732", "False Claims Act — false claims jurisdiction", ["fca"]),
    (31, "3733", "31 U.S.C. § 3733", "False Claims Act — civil investigative demands", ["fca"]),
    (42, "1395dd", "42 U.S.C. § 1395dd", "EMTALA — examination and treatment for emergency medical conditions and women in labor", ["emtala"]),
    (42, "1320d", "42 U.S.C. § 1320d", "HIPAA — definitions (administrative simplification)", ["hipaa"]),
    (42, "1320d-2", "42 U.S.C. § 1320d-2", "HIPAA — standards for information transactions and data elements", ["hipaa"]),
    (42, "1320d-5", "42 U.S.C. § 1320d-5", "HIPAA — general penalty for failure to comply", ["hipaa"]),
    (42, "1320d-6", "42 U.S.C. § 1320d-6", "HIPAA — wrongful disclosure of individually identifiable health information", ["hipaa"]),
    # ── insurance / payer ──
    (29, "1132", "29 U.S.C. § 1132", "ERISA — civil enforcement of employee benefit plans", ["erisa", "insurance"]),
    (29, "1144", "29 U.S.C. § 1144", "ERISA — preemption of State laws", ["erisa", "insurance"]),
    (29, "1185a", "29 U.S.C. § 1185a", "ERISA — parity in mental health and substance use disorder benefits", ["parity", "insurance"]),
    (29, "1181", "29 U.S.C. § 1181", "ERISA — increased portability through limitation on preexisting condition exclusions", ["erisa", "insurance"]),
    (42, "300gg", "42 U.S.C. § 300gg", "PHSA — fair health insurance premiums", ["aca", "insurance"]),
    (42, "300gg-13", "42 U.S.C. § 300gg-13", "PHSA — coverage of preventive health services", ["aca", "insurance"]),
    (42, "300gg-19a", "42 U.S.C. § 300gg-19a", "PHSA — internal claims, appeals and external review", ["insurance"]),
    (42, "300gg-26", "42 U.S.C. § 300gg-26", "PHSA — parity in mental health and substance use disorder benefits", ["parity", "insurance"]),
    (42, "300gg-111", "42 U.S.C. § 300gg-111", "No Surprises Act — preventing surprise medical bills", ["nsa", "insurance"]),
    (42, "300gg-131", "42 U.S.C. § 300gg-131", "No Surprises Act — balance billing in cases of emergency services", ["nsa", "insurance"]),
]

# (title, part, practice_area[], label) — fetched whole, split into per-section docs
CFR = [
    (42, "411", ["stark"], "Exclusions from Medicare and limitations on Medicare payment (incl. Stark exceptions, subpart J)"),
    (42, "1001", ["aks"], "OIG program integrity — exclusions and Anti-Kickback safe harbors (§ 1001.952)"),
    (42, "489", ["emtala"], "Provider agreements and supplier approval (EMTALA, § 489.24)"),
    (42, "2", ["part2", "sud"], "Confidentiality of substance use disorder patient records"),
    (45, "164", ["hipaa"], "HIPAA Privacy, Security, and Breach Notification Rules"),
    (45, "160", ["hipaa"], "HIPAA general administrative requirements & enforcement"),
    (45, "162", ["hipaa"], "HIPAA administrative requirements — transactions and code sets"),
    (42, "1003", ["cmp"], "Office of Inspector General — civil money penalties"),
    (42, "1002", ["exclusion"], "Program integrity — State-initiated exclusions from Medicaid"),
    (42, "1008", ["oig"], "OIG advisory opinion procedures"),
    (42, "1006", ["oig"], "OIG investigational inquiries and subpoenas"),
    (42, "455", ["cmp"], "Medicaid program integrity"),
    # ── insurance / payer ──
    (45, "147", ["aca", "insurance"], "PHSA market reforms — group & individual health insurance"),
    (45, "149", ["nsa", "insurance"], "No Surprises Act — surprise billing protections"),
    (45, "156", ["aca", "insurance"], "Health insurance issuer standards — essential benefits & QHPs"),
    (45, "158", ["mlr", "insurance"], "Medical loss ratio — issuer reporting and rebates"),
    (29, "2560", ["erisa", "insurance"], "ERISA — claims procedure and enforcement regulations"),
    (42, "422", ["medicare-advantage", "insurance"], "Medicare Advantage program"),
    (42, "423", ["medicare-advantage", "insurance"], "Medicare Part D — prescription drug benefit"),
    (42, "438", ["managed-care", "insurance"], "Medicaid managed care"),
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _get(client, url, params=None):
    r = await client.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r


def clean_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"&#?\w+;", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def extract_usc(html: str) -> str:
    """Pull the statutory body out of an LII U.S. Code page (the .text div)."""
    i = html.find('class="text"')
    if i != -1:
        i = html.find(">", i) + 1  # start after the div tag
    text = clean_html(html[i:] if i != -1 else html)
    # cut LII chrome / toolbox footer (keep Editorial & Statutory Notes — useful)
    for marker in ("U.S. Code Toolbox", "How current is this", "U.S. Code Toolbox",
                   "Accessibility", "LII has no control"):
        j = text.find(marker)
        if j > 800:
            text = text[:j]
            break
    return text.strip()


async def latest_date(client, title: int) -> str:
    r = await _get(client, f"{ECFR}/titles.json")
    for t in r.json()["titles"]:
        if t["number"] == title:
            return t["latest_issue_date"]
    return "2024-12-31"


def parse_cfr(xml_text: str, title: int, part: str, areas: list) -> list[dict]:
    """Split a CFR part's eCFR XML into per-section documents."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    docs = []
    for sec in root.iter("DIV8"):  # DIV8 = SECTION
        num = sec.get("N", "")
        head = "".join(sec.find("HEAD").itertext()).strip() if sec.find("HEAD") is not None else ""
        # all paragraph text under the section
        parts = []
        for el in sec.iter():
            if el.tag in ("P", "PSPACE", "FP") and el.text is not None:
                parts.append("".join(el.itertext()))
        text = re.sub(r"\s+", " ", (head + "\n" + "\n".join(parts))).strip()
        if len(text) < 120:
            continue
        cite = f"{title} CFR § {num}"
        docs.append({
            "doc_id": f"cfr-{title}-{num}",
            "source": "ecfr", "doc_type": "regulation", "jurisdiction": "US",
            "title": head or cite, "citation": cite,
            "url": f"https://www.ecfr.gov/current/title-{title}/part-{part}/section-{num}",
            "practice_area": areas, "cites": [], "text": text,
        })
    return docs


async def run():
    n = 0
    f = OUT.open("w")
    async with httpx.AsyncClient(headers=UA, follow_redirects=True) as client:
        # ── statutes (USC via LII) ──
        print("→ U.S. Code (LII)")
        for title, sec, cite, heading, areas in USC:
            try:
                r = await _get(client, f"{LII}/{title}/{sec}")
                text = extract_usc(r.text)
            except Exception as e:
                print(f"  ✗ {cite}: {e}", file=sys.stderr)
                continue
            if len(text) < 200:
                print(f"  thin {cite} ({len(text)})", file=sys.stderr)
            rec = {
                "doc_id": f"usc-{title}-{sec}", "source": "usc", "doc_type": "statute",
                "jurisdiction": "US", "title": f"{cite} — {heading}", "citation": cite,
                "url": f"{LII}/{title}/{sec}", "practice_area": areas, "cites": [], "text": text,
            }
            f.write(json.dumps(rec) + "\n"); f.flush(); n += 1
            print(f"  ✓ {cite} ({len(text)} chars)", flush=True)

        # ── regulations (CFR via eCFR) ──
        print("→ CFR (eCFR API)")
        for title, part, areas, label in CFR:
            try:
                date = await latest_date(client, title)
                r = await _get(client, f"{ECFR}/full/{date}/title-{title}.xml", {"part": part})
                docs = parse_cfr(r.text, title, part, areas)
            except Exception as e:
                print(f"  ✗ {title} CFR {part}: {e}", file=sys.stderr)
                continue
            for d in docs:
                f.write(json.dumps(d) + "\n"); n += 1
            f.flush()
            print(f"  ✓ {title} CFR Part {part} — {len(docs)} sections ({label[:40]})", flush=True)
    f.close()
    print(f"✓ {n} healthcare documents → {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
