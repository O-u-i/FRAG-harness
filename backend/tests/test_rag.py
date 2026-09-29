from pathlib import Path

from fastapi.testclient import TestClient

from frag_api.main import create_app

DATASET = {"datasetId": "synthetic-risk-review-v1"}


def test_rag_build_search_preview_run_evaluate(tmp_path: Path):
    with TestClient(create_app(rag_index_path=tmp_path / "rag.sqlite3", plugin_root=tmp_path / "plugins"), raise_server_exceptions=False) as client:
        assert client.get("/api/rag/status").json()["state"] == "not_built"
        assert client.post("/api/rag/search", json={**DATASET, "query": "regulatory risk"}).status_code == 409
        built = client.post("/api/rag/index/rebuild", json=DATASET)
        assert built.status_code == 200, built.text
        assert built.json()["chunkCount"] == 3
        body = {**DATASET, "query": "What regulatory risks are mentioned?", "topK": 3}
        search = client.post("/api/rag/search", json=body)
        assert search.status_code == 200
        assert search.json()["results"][0]["chunkId"].endswith("c002")
        preview = client.post("/api/rag/preview", json=body).json()
        first = preview["retrievalResults"][0]
        assert first["parentId"].endswith("parent-002")
        assert first["evidenceId"] in {item["chunkId"] for item in preview["candidateEvidence"]}
        assert first["evidenceId"] != first["chunkId"]
        run_body = {**body, "contextFingerprint": preview["contextFingerprint"], "approvalToken": preview["approvalToken"], "approved": True}
        run = client.post("/api/rag/run", json=run_body)
        assert run.status_code == 200, run.text
        assert "inferenceStage" not in run.json()
        second = run.json()["inferencePreview"]
        inference_body = {"contextFingerprint": preview["contextFingerprint"],
                          "inferenceFingerprint": second["inferenceFingerprint"],
                          "approvalToken": second["approvalToken"], "approved": True}
        answer = client.post("/api/rag/inference/run", json=inference_body)
        assert answer.status_code == 200
        evidence_ids = {item["chunkId"] for item in preview["candidateEvidence"]}
        assert all(set(claim["chunkIds"]).issubset(evidence_ids) for claim in answer.json()["result"]["claims"])
        assert client.post("/api/rag/inference/run", json=inference_body).status_code == 409
        assert client.post("/api/rag/run", json=run_body).status_code == 409
        evaluation = client.post("/api/rag/evaluations/run", json=DATASET)
        assert evaluation.status_code == 200
        assert evaluation.json()["status"] == "PASS"


def test_rag_index_detects_source_changes(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    document = root / "synthetic-risk-review.md"
    document.write_text("# Risk\nRegulatory restrictions increased.", encoding="utf-8")
    (root / "eval-cases.json").write_text('{"suiteVersion":"v1","datasetId":"synthetic-risk-review-v1","cases":[]}', encoding="utf-8")
    with TestClient(create_app(rag_index_path=tmp_path / "rag.sqlite3", rag_source_root=root, plugin_root=tmp_path / "plugins"), raise_server_exceptions=False) as client:
        assert client.post("/api/rag/index/rebuild", json=DATASET).status_code == 200
        document.write_text("# Risk\nChanged content.", encoding="utf-8")
        assert client.get("/api/rag/status").json()["state"] == "stale"
        assert client.post("/api/rag/search", json={**DATASET, "query": "regulatory"}).status_code == 409


def test_rag_source_change_blocks_second_stage(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    document = source / "synthetic-risk-review.md"
    document.write_text("# Risk\nRegulatory restrictions increased.", encoding="utf-8")
    with TestClient(create_app(rag_index_path=tmp_path / "rag.sqlite3", rag_source_root=source,
                               plugin_root=tmp_path / "plugins"), raise_server_exceptions=False) as client:
        assert client.post("/api/rag/index/rebuild", json=DATASET).status_code == 200
        body = {**DATASET, "query": "regulatory restrictions", "topK": 1}
        preview = client.post("/api/rag/preview", json=body).json()
        context = client.post("/api/rag/run", json={**body, "contextFingerprint": preview["contextFingerprint"],
            "approvalToken": preview["approvalToken"], "approved": True}).json()
        document.write_text("# Risk\nRegulatory restrictions changed.", encoding="utf-8")
        second = context["inferencePreview"]
        result = client.post("/api/rag/inference/run", json={"contextFingerprint": preview["contextFingerprint"],
            "inferenceFingerprint": second["inferenceFingerprint"], "approvalToken": second["approvalToken"],
            "approved": True})
        assert result.status_code == 409
