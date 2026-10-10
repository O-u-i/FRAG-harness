from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from pathlib import Path

from frag_api.errors import RagIndexBuildError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAG_INDEX_PATH = REPOSITORY_ROOT / ".local-index" / "rag.sqlite3"


@dataclass(frozen=True)
class IndexDocument:
    document_id: str
    dataset_id: str
    source_id: str
    source_hash: str


@dataclass(frozen=True)
class IndexChunk:
    chunk_id: str
    document_id: str
    source_id: str
    locator_id: str
    locator_label: str
    ordinal: int
    text: str
    text_hash: str
    parent_id: str
    search_text: str


@dataclass(frozen=True)
class IndexParent:
    parent_id: str
    document_id: str
    locator_id: str
    locator_label: str
    title_path: str
    text: str


@dataclass(frozen=True)
class IndexSnapshot:
    document_count: int
    chunk_count: int
    source_hash: str | None
    index_revision: str | None
    schema_version: str | None = None


@dataclass(frozen=True)
class SearchRow:
    chunk_id: str
    document_id: str
    source_id: str
    locator_id: str
    locator_label: str
    text: str
    text_hash: str
    bm25_score: float
    parent_id: str


class RagIndexRepository:
    def __init__(self, path: str | Path = DEFAULT_RAG_INDEX_PATH):
        self.path = Path(path)

    def snapshot(self) -> IndexSnapshot:
        if not self.path.exists():
            return IndexSnapshot(0, 0, None, None)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN")
                if not self._has_schema(connection):
                    return IndexSnapshot(0, 0, None, None)
                return self._snapshot(connection)
        except sqlite3.Error as error:
            raise RagIndexBuildError() from error

    def rebuild(
        self,
        documents: list[IndexDocument],
        chunks: list[IndexChunk],
        parents: list[IndexParent],
        index_revision: str,
        manifest: dict,
    ) -> IndexSnapshot:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            self._create_schema(connection)
            version = connection.execute("SELECT value FROM rag_meta WHERE key='schema_version'").fetchone()
            if version and version[0] != "2":
                connection.execute("DROP TABLE IF EXISTS rag_chunks_fts")
                connection.execute("DROP TABLE IF EXISTS rag_chunks")
                connection.execute("DROP TABLE IF EXISTS rag_parents")
                connection.execute("DROP TABLE IF EXISTS rag_documents")
                self._create_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM rag_chunks_fts")
            connection.execute("DELETE FROM rag_chunks")
            connection.execute("DELETE FROM rag_parents")
            connection.execute("DELETE FROM rag_documents")
            connection.executemany(
                """
                INSERT INTO rag_documents
                  (document_id, dataset_id, source_id, source_hash, chunk_strategy_version)
                VALUES (?, ?, ?, ?, 'markdown-hierarchy-v2')
                """,
                [(document.document_id, document.dataset_id, document.source_id, document.source_hash) for document in documents],
            )
            connection.executemany(
                """INSERT INTO rag_parents
                   (parent_id, document_id, locator_id, locator_label, title_path, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(p.parent_id, p.document_id, p.locator_id, p.locator_label, p.title_path, p.text)
                 for p in parents],
            )
            connection.executemany(
                """
                INSERT INTO rag_chunks
                  (chunk_id, document_id, source_id, locator_id, locator_label,
                   ordinal, content, content_hash, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source_id,
                        chunk.locator_id,
                        chunk.locator_label,
                        chunk.ordinal,
                        chunk.text,
                        chunk.text_hash,
                        chunk.parent_id,
                    )
                    for chunk in chunks
                ],
            )
            connection.executemany(
                "INSERT INTO rag_chunks_fts (chunk_id, content) VALUES (?, ?)",
                [(chunk.chunk_id, chunk.search_text) for chunk in chunks],
            )
            connection.executemany(
                "INSERT OR REPLACE INTO rag_meta (key, value) VALUES (?, ?)",
                [
                    ("schema_version", "2"),
                    ("source_hash", index_revision),
                    ("index_revision", index_revision),
                    ("manifest", json.dumps(manifest, ensure_ascii=False)),
                ],
            )
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise RagIndexBuildError() from error
        finally:
            connection.close()
        return self.snapshot()

    def search_snapshot(self, match_expression: str, top_k: int) -> tuple[IndexSnapshot, list[SearchRow], dict[str, IndexParent]]:
        """Revision, hits and selected parents share one SQLite read transaction."""
        try:
            with self._connect() as connection:
                connection.execute("BEGIN")
                snapshot = self._snapshot(connection)
                rows = connection.execute(
                    """
                    SELECT c.chunk_id, c.document_id, c.source_id, c.locator_id,
                           c.locator_label, c.content, c.content_hash,
                           bm25(rag_chunks_fts) AS bm25_score, c.parent_id
                    FROM rag_chunks_fts
                    JOIN rag_chunks AS c ON c.chunk_id = rag_chunks_fts.chunk_id
                    WHERE rag_chunks_fts MATCH ?
                    ORDER BY bm25_score ASC, c.document_id ASC, c.ordinal ASC, c.chunk_id ASC
                    """,
                    (match_expression,),
                )
                hits, seen = [], set()
                for row in rows:
                    hit = SearchRow(*row)
                    if hit.parent_id in seen:
                        continue
                    hits.append(hit)
                    seen.add(hit.parent_id)
                    if len(hits) == top_k:
                        break
                parents = {}
                for parent_id in dict.fromkeys(item.parent_id for item in hits):
                    row = connection.execute(
                        "SELECT parent_id, document_id, locator_id, locator_label, title_path, content "
                        "FROM rag_parents WHERE parent_id = ?", (parent_id,),
                    ).fetchone()
                    if row is None:
                        raise RagIndexBuildError()
                    parents[parent_id] = IndexParent(*row)
            return snapshot, hits, parents
        except sqlite3.Error as error:
            raise RagIndexBuildError() from error

    @staticmethod
    def _snapshot(connection: sqlite3.Connection) -> IndexSnapshot:
        metadata = dict(connection.execute("SELECT key, value FROM rag_meta"))
        return IndexSnapshot(
            document_count=connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0],
            chunk_count=connection.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0],
            source_hash=metadata.get("source_hash"), index_revision=metadata.get("index_revision"),
            schema_version=metadata.get("schema_version"),
        )

    @staticmethod
    def _has_schema(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rag_meta'"
        ).fetchone()
        return row is not None

    def parent(self, parent_id: str) -> IndexParent:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT parent_id, document_id, locator_id, locator_label, title_path, content "
                    "FROM rag_parents WHERE parent_id = ?", (parent_id,),
                ).fetchone()
            if row is None:
                raise RagIndexBuildError()
            return IndexParent(*row)
        except sqlite3.Error as error:
            raise RagIndexBuildError() from error

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rag_documents (
              document_id TEXT PRIMARY KEY,
              dataset_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              source_hash TEXT NOT NULL,
              chunk_strategy_version TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rag_chunks (
              chunk_id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES rag_documents(document_id),
              source_id TEXT NOT NULL,
              locator_id TEXT NOT NULL,
              locator_label TEXT NOT NULL,
              ordinal INTEGER NOT NULL,
              content TEXT NOT NULL,
              content_hash TEXT NOT NULL
              ,parent_id TEXT NOT NULL REFERENCES rag_parents(parent_id)
            );
            CREATE TABLE IF NOT EXISTS rag_parents (
              parent_id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES rag_documents(document_id),
              locator_id TEXT NOT NULL,
              locator_label TEXT NOT NULL,
              title_path TEXT NOT NULL,
              content TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
              chunk_id UNINDEXED,
              content,
              tokenize='porter unicode61 remove_diacritics 2'
            );
            """
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
