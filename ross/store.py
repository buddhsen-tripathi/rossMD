"""ClickHouse: the corpus, the vector index, the blackboard, the audit trail.

One store doing four jobs:
  documents  — full text of cases/statutes/regs + metadata + citation edges
  chunks     — embedded passages (vector column) for semantic retrieval
  runs       — one row per Ross run (the blackboard snapshot, JSON)
  traces     — every agent event (audit trail + the live theater feed)

Vector search uses ClickHouse cosineDistance over Array(Float32).
"""
from __future__ import annotations

import clickhouse_connect

from ross.config import CH, EMBED_DIM

_client = None


def client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(**CH)
    return _client


SCHEMA = [
    # ── corpus ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id        String,
        source        LowCardinality(String),
        doc_type      LowCardinality(String),   -- case | statute | regulation | admin_code
        jurisdiction  LowCardinality(String),
        title         String,                   -- case name / statute heading
        citation      String,                   -- primary citation string
        court         String,
        date_filed    Nullable(Date32),         -- Date32: 1900+ (case law predates 1970)
        url           String,
        text          String,
        cites         Array(String),            -- outbound citation edges (graph-as-array)
        practice_area Array(LowCardinality(String)),
        ingested_at   DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(ingested_at)
    ORDER BY doc_id
    """,
    # ── vector index ──────────────────────────────────────────────────
    f"""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id   String,
        doc_id     String,
        seq        UInt32,
        doc_type   LowCardinality(String),
        title      String,
        citation   String,
        url        String,
        text       String,
        embedding  Array(Float32),
        CONSTRAINT emb_dim CHECK length(embedding) = {EMBED_DIM}
    ) ENGINE = MergeTree()
    ORDER BY (doc_id, seq)
    """,
    # ── runtime blackboard ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id     String,
        created_at DateTime DEFAULT now(),
        scenario   String,
        status     LowCardinality(String),
        blackboard String                       -- JSON snapshot of the full run
    ) ENGINE = ReplacingMergeTree(created_at)
    ORDER BY run_id
    """,
    # ── audit trail / live feed ───────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS traces (
        run_id    String,
        ts        DateTime64(3) DEFAULT now64(3),
        seq       UInt32,
        agent     LowCardinality(String),
        event     LowCardinality(String),
        payload   String                        -- JSON
    ) ENGINE = MergeTree()
    ORDER BY (run_id, seq)
    """,
]


def init_db():
    c = clickhouse_connect.get_client(
        host=CH["host"], port=CH["port"], username=CH["username"],
        password=CH["password"], secure=CH["secure"],
    )
    c.command(f"CREATE DATABASE IF NOT EXISTS {CH['database']}")
    cc = client()
    for ddl in SCHEMA:
        cc.command(ddl)
    print("✓ schema ready:", ", ".join(["documents", "chunks", "runs", "traces"]))


def vector_search(query_embedding: list[float], k: int = 8,
                  doc_type: str | None = None,
                  areas: list[str] | None = None) -> list[dict]:
    """Top-k chunks by cosine similarity.

    Optionally scope to a regulatory regime: when `areas` is given, join to
    documents and keep only chunks whose document is tagged with one of those
    practice areas (e.g. an AKS issue retrieves AKS/OIG authority, not a random
    Part D section)."""
    if areas:
        arr = "[" + ",".join(f"'{a}'" for a in areas) + "]"
        sql = f"""
            SELECT c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.title AS title,
                   c.citation AS citation, c.url AS url, c.text AS text,
                   cosineDistance(c.embedding, {query_embedding}) AS dist
            FROM chunks c
            INNER JOIN documents d ON c.doc_id = d.doc_id
            WHERE hasAny(d.practice_area, {arr})
            ORDER BY dist ASC
            LIMIT {k}
        """
    else:
        where = f"WHERE doc_type = '{doc_type}'" if doc_type else ""
        sql = f"""
            SELECT chunk_id, doc_id, title, citation, url, text,
                   cosineDistance(embedding, {query_embedding}) AS dist
            FROM chunks
            {where}
            ORDER BY dist ASC
            LIMIT {k}
        """
    res = client().query(sql)
    cols = res.column_names
    return [dict(zip(cols, row)) for row in res.result_rows]


if __name__ == "__main__":
    init_db()
