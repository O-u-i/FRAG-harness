import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from frag_api.main import create_app
from frag_api.services.rag_markdown import CHILD_SIZE, children_for, sections_from_markdown

DATASET = {"datasetId": "synthetic-risk-review-v1"}


def test_explicit_rebuild_removes_replaced_parent_child_and_fts_content(tmp_path: Path):
    sources = tmp_path / 'replacement-source'
    sources.mkdir()
    document = sources / 'synthetic-risk-review.md'
    document.write_text('# Legacy\nlegacyneedle identifies the old synthetic source.',encoding='utf-8')
    index = tmp_path / 'replacement.sqlite3'
    app = create_app(rag_source_root=sources,rag_index_path=index,plugin_root=tmp_path/'plugins')
    with TestClient(app,raise_server_exceptions=False) as client:
        first = client.post('/api/rag/index/rebuild',json=DATASET).json()
        assert client.post('/api/rag/search',json={**DATASET,'query':'legacyneedle'}).json()['results']
        document.write_text('# Current\nfreshneedle identifies the replacement synthetic source.',encoding='utf-8')
        assert client.post('/api/rag/search',json={**DATASET,'query':'legacyneedle'}).status_code == 409
        second = client.post('/api/rag/index/rebuild',json=DATASET).json()
        assert second['indexRevision'] != first['indexRevision'] and second['sourceHash'] != first['sourceHash']
        assert client.post('/api/rag/search',json={**DATASET,'query':'legacyneedle'}).json()['results'] == []
        assert client.post('/api/rag/search',json={**DATASET,'query':'freshneedle'}).json()['results']
    with sqlite3.connect(index) as connection:
        for table in ('rag_parents','rag_chunks','rag_chunks_fts'):
            rows = connection.execute(f'SELECT content FROM {table}').fetchall()
            assert rows and all('legacyneedle' not in row[0] for row in rows)


def test_markdown_structure_and_recursive_children():
    source = ("---\n# YAML comment\nstate: ready\n---\nIntroduction.\n"
              "# Root\n## Detail\n```md\n# Not a heading\n```\n" +
              "First sentence. Second sentence.\n\n" + "LongLine" * 130 +
              "\n### Next\nEnd.\n")
    sections = sections_from_markdown(source)
    assert [section.label for section in sections] == ["Document preamble", "Root", "Detail", "Next"]
    assert sections[2].title_path == "Root > Detail"
    assert "# Not a heading" in sections[2].text
    children = children_for(sections[2])
    assert len(children) > 2
    assert all(child.text.startswith("Title path: Root > Detail\n") for child in children)
    assert all(len(child.text) <= CHILD_SIZE for child in children)
    assert children[0].text[-80:] in children[1].text
    trailing_separator = sections_from_markdown("# Long\n" + "word " * 200 + "\n\n")
    assert len(children_for(trailing_separator[0])) > 1


def test_chinese_search_parent_dedupe_and_bounded_window(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    body = "监管风险显著增加。\n\n" * 250
    (root / "synthetic-risk-review.md").write_text(
        "# 风险复核\n## 监管风险\n" + body, encoding="utf-8",
    )
    with TestClient(create_app(rag_index_path=tmp_path / "rag.sqlite3", rag_source_root=root,
                               plugin_root=tmp_path / "plugins"), raise_server_exceptions=False) as client:
        built = client.post("/api/rag/index/rebuild", json=DATASET)
        assert built.status_code == 200, built.text
        assert built.json()["chunkCount"] > 3
        query = {**DATASET, "query": "监管风险", "topK": 10}
        search = client.post("/api/rag/search", json=query)
        assert search.status_code == 200, search.text
        assert search.json()["results"]
        preview = client.post("/api/rag/preview", json=query)
        assert preview.status_code == 200, preview.text
        result = preview.json()
        assert len(result["candidateEvidence"]) == 1
        evidence = result["candidateEvidence"][0]
        assert evidence["evidenceId"].startswith(search.json()["results"][0]["parentId"])
        assert "[Parent section window" in evidence["text"]
        assert "风险复核 > 监管风险" in evidence["text"]
        assert all(row["evidenceId"] == evidence["evidenceId"] for row in result["retrievalResults"])
        assert result["budget"]["estimatedInputTokens"] <= 4500


def test_old_derived_index_requires_explicit_rebuild(tmp_path: Path):
    index = tmp_path / "rag.sqlite3"
    with sqlite3.connect(index) as connection:
        connection.executescript("""
            CREATE TABLE rag_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE rag_documents (document_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
              source_id TEXT NOT NULL, source_hash TEXT NOT NULL, chunk_strategy_version TEXT NOT NULL);
            CREATE TABLE rag_chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
              source_id TEXT NOT NULL, locator_id TEXT NOT NULL, locator_label TEXT NOT NULL,
              ordinal INTEGER NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL);
            CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(chunk_id UNINDEXED, content);
            INSERT INTO rag_meta VALUES ('schema_version', '1');
            INSERT INTO rag_meta VALUES ('index_revision', 'legacy');
        """)
    with TestClient(create_app(rag_index_path=index, plugin_root=tmp_path / "plugins"),
                    raise_server_exceptions=False) as client:
        assert client.get("/api/rag/status").json()["state"] == "stale"
        assert client.post("/api/rag/search", json={**DATASET, "query": "risk"}).status_code == 409
        rebuilt = client.post("/api/rag/index/rebuild", json=DATASET)
        assert rebuilt.status_code == 200, rebuilt.text
        assert rebuilt.json()["schemaVersion"] == 2
