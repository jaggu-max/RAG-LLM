"""Database layer — SQLite for metadata/FTS, ChromaDB for vectors."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ── SQLite ────────────────────────────────────────────────

_db_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id            TEXT PRIMARY KEY,
                    filename      TEXT NOT NULL,
                    file_type     TEXT NOT NULL,
                    file_path     TEXT NOT NULL,
                    size_bytes    INTEGER DEFAULT 0,
                    file_hash     TEXT NOT NULL,
                    chunks        INTEGER DEFAULT 0,
                    status        TEXT DEFAULT 'pending',
                    dataset_type  TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    created_at    TEXT NOT NULL,
                    indexed_at    TEXT,
                    updated_at    TEXT
                );

                CREATE TABLE IF NOT EXISTS queries (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    question        TEXT NOT NULL,
                    answer_type     TEXT NOT NULL,
                    confidence      REAL DEFAULT 0,
                    model           TEXT DEFAULT '',
                    response_time   INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id,
                    document_id,
                    text,
                    file_name,
                    content='',
                    tokenize='porter unicode61'
                );
            """)
            conn.commit()
        finally:
            conn.close()
    log.info("SQLite database initialized at %s", settings.DB_PATH)


# ── Document CRUD ─────────────────────────────────────────

def insert_document(doc: Dict[str, Any]) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, filename, file_type, file_path, size_bytes, file_hash,
                    chunks, status, dataset_type, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc["id"], doc["filename"], doc["file_type"], doc["file_path"],
                 doc.get("size_bytes", 0), doc["file_hash"],
                 doc.get("chunks", 0), doc.get("status", "pending"),
                 doc.get("dataset_type", ""),
                 doc.get("created_at", datetime.now(timezone.utc).isoformat()),
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


def update_document(doc_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [doc_id]
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(f"UPDATE documents SET {set_clause} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_document_by_path(file_path: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM documents WHERE file_path = ?", (file_path,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_document_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_documents() -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_document(doc_id: str) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
        finally:
            conn.close()


# ── FTS5 keyword index ───────────────────────────────────

def insert_fts_chunks(chunks: List[Dict[str, Any]]) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executemany(
                "INSERT INTO chunks_fts (chunk_id, document_id, text, file_name) VALUES (?, ?, ?, ?)",
                [(c["chunk_id"], c["document_id"], c["text"], c.get("file_name", "")) for c in chunks],
            )
            conn.commit()
        finally:
            conn.close()


def delete_fts_by_document(doc_id: str) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM chunks_fts WHERE document_id = ?", (doc_id,))
            conn.commit()
        finally:
            conn.close()


def search_fts(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Full-text keyword search returning chunk_id, document_id, rank."""
    conn = _get_conn()
    try:
        # Escape special chars for FTS5
        safe_query = query.replace('"', '""')
        rows = conn.execute(
            """SELECT chunk_id, document_id, text, file_name, rank
               FROM chunks_fts
               WHERE chunks_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (f'"{safe_query}"', limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        # Fallback: try simpler query
        try:
            terms = query.split()
            if not terms:
                return []
            fts_query = " OR ".join(f'"{t}"' for t in terms if t.strip())
            rows = conn.execute(
                """SELECT chunk_id, document_id, text, file_name, rank
                   FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
    finally:
        conn.close()


# ── Query logging ─────────────────────────────────────────

def log_query(question: str, answer_type: str, confidence: float,
              model: str, response_time: int) -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO queries (question, answer_type, confidence, model,
                   response_time, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (question, answer_type, confidence, model, response_time,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


def get_query_stats() -> Dict[str, Any]:
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT COUNT(*) as total,
                      COALESCE(AVG(response_time), 0) as avg_time,
                      COALESCE(AVG(confidence), 0) as avg_conf
               FROM queries"""
        ).fetchone()
        return dict(row) if row else {"total": 0, "avg_time": 0, "avg_conf": 0}
    finally:
        conn.close()


def get_document_stats() -> Dict[str, Any]:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        indexed = conn.execute("SELECT COUNT(*) as c FROM documents WHERE status='indexed'").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) as c FROM documents WHERE status IN ('pending','processing')").fetchone()["c"]
        failed = conn.execute("SELECT COUNT(*) as c FROM documents WHERE status='failed'").fetchone()["c"]
        chunks = conn.execute("SELECT COALESCE(SUM(chunks), 0) as c FROM documents").fetchone()["c"]
        size = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) as c FROM documents").fetchone()["c"]
        by_type = conn.execute(
            "SELECT file_type, COUNT(*) as count FROM documents GROUP BY file_type"
        ).fetchall()
        return {
            "total": total, "indexed": indexed, "pending": pending,
            "failed": failed, "chunks": chunks, "size": size,
            "by_type": [dict(r) for r in by_type],
        }
    finally:
        conn.close()


# ── ChromaDB ──────────────────────────────────────────────

_chroma_client: Optional[chromadb.ClientAPI] = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        log.info("ChromaDB client initialized at %s", settings.CHROMA_PATH)
    return _chroma_client


def get_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def add_to_chroma(ids: List[str], embeddings: List[List[float]],
                   documents: List[str], metadatas: List[Dict[str, Any]]) -> None:
    collection = get_collection()
    # ChromaDB batch limit is 5000
    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        end = i + batch_size
        collection.add(
            ids=ids[i:end],
            embeddings=embeddings[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end],
        )


def query_chroma(query_embedding: List[float], n_results: int = 10,
                  where: Optional[Dict] = None) -> Dict[str, Any]:
    collection = get_collection()
    kwargs: Dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def delete_from_chroma(document_id: str) -> None:
    collection = get_collection()
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as e:
        log.warning("ChromaDB delete for %s: %s", document_id, e)


def chroma_count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0
