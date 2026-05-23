"""JSONL → chunks → embeddings → ClickHouse.

Reads everything in data/raw/*.jsonl, normalizes to documents, splits text
into overlapping passages, embeds locally, and writes documents + chunks.

Run:  uv run python -m ross.corpus.ingest
"""
import hashlib
import json
import re
import sys
from datetime import date

from ross.config import DATA_RAW
from ross.embed import embed
from ross.store import client, init_db

CHUNK_CHARS = 1400
OVERLAP = 200
EMBED_BATCH = 256


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:20]


def split(text: str) -> list[str]:
    text = re.sub(r"\s+\n", "\n", text or "").strip()
    if not text:
        return []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - OVERLAP
    return out


def normalize(rec: dict) -> dict:
    """Map a raw scraped record to the documents schema."""
    if rec.get("source") == "courtlistener":
        cid = rec.get("cluster_id")
        cites = rec.get("citations") or []
        return {
            "doc_id": _id("cl", cid),
            "source": "courtlistener",
            "doc_type": "case",
            "jurisdiction": "NY",
            "title": rec.get("case_name") or "",
            "citation": cites[0] if cites else "",
            "court": rec.get("court") or "",
            "date_filed": rec.get("date_filed"),
            "url": rec.get("url") or "",
            "text": rec.get("text") or rec.get("snippet") or "",
            "cites": [],  # case→authority edges parsed in a later pass
            "practice_area": [],
        }
    # statutes / admin code / regs (task #2 writer)
    return {
        "doc_id": rec.get("doc_id") or _id(rec.get("source"), rec.get("citation"), rec.get("title")),
        "source": rec.get("source", "unknown"),
        "doc_type": rec.get("doc_type", "statute"),
        "jurisdiction": rec.get("jurisdiction", "NY"),
        "title": rec.get("title", ""),
        "citation": rec.get("citation", ""),
        "court": rec.get("court", ""),
        "date_filed": rec.get("date_filed"),
        "url": rec.get("url", ""),
        "text": rec.get("text", ""),
        "cites": rec.get("cites", []),
        "practice_area": rec.get("practice_area", []),
    }


def _parse_date(s):
    if not s:
        return None
    try:
        d = date.fromisoformat(s[:10])
    except ValueError:
        return None
    # ClickHouse Date32 range is 1900-01-01 .. 2299-12-31
    return d if 1900 <= d.year <= 2299 else None


def run():
    init_db()
    files = sorted(DATA_RAW.glob("*.jsonl"))
    if not files:
        print("no raw JSONL in data/raw/ — run a scraper first", file=sys.stderr)
        return

    c = client()
    # idempotent: re-running ingest replaces the corpus rather than duplicating
    c.command("TRUNCATE TABLE IF EXISTS documents")
    c.command("TRUNCATE TABLE IF EXISTS chunks")

    DOC_COLS = ["doc_id", "source", "doc_type", "jurisdiction", "title",
                "citation", "court", "date_filed", "url", "text",
                "cites", "practice_area"]
    CHUNK_COLS = ["chunk_id", "doc_id", "seq", "doc_type", "title",
                  "citation", "url", "text", "embedding"]

    seen_docs = set()
    pending_text, pending_meta = [], []
    n_docs = n_chunks = 0

    def flush_embeddings():
        nonlocal n_chunks
        if not pending_text:
            return
        vecs = embed(pending_text)
        rows = [[*meta, vec] for meta, vec in zip(pending_meta, vecs)]
        c.insert("chunks", rows, column_names=CHUNK_COLS)   # stream insert
        n_chunks += len(rows)
        pending_text.clear()
        pending_meta.clear()
        print(f"  … {n_docs} docs, {n_chunks} chunks", flush=True)

    doc_batch = []
    for fp in files:
        for line in fp.open():
            line = line.strip()
            if not line:
                continue
            d = normalize(json.loads(line))
            if d["doc_id"] in seen_docs or not d["text"]:
                continue
            seen_docs.add(d["doc_id"])
            doc_batch.append([
                d["doc_id"], d["source"], d["doc_type"], d["jurisdiction"],
                d["title"], d["citation"], d["court"], _parse_date(d["date_filed"]),
                d["url"], d["text"], d["cites"], d["practice_area"],
            ])
            n_docs += 1
            if len(doc_batch) >= 500:
                c.insert("documents", doc_batch, column_names=DOC_COLS)
                doc_batch = []
            for seq, passage in enumerate(split(d["text"])):
                pending_text.append(f"{d['title']} {d['citation']}\n{passage}")
                pending_meta.append([
                    _id(d["doc_id"], seq), d["doc_id"], seq, d["doc_type"],
                    d["title"], d["citation"], d["url"], passage,
                ])
                if len(pending_text) >= EMBED_BATCH:
                    flush_embeddings()
    if doc_batch:
        c.insert("documents", doc_batch, column_names=DOC_COLS)
    flush_embeddings()
    print(f"✓ ingested {n_docs} docs, {n_chunks} chunks")


if __name__ == "__main__":
    run()
