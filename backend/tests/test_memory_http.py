"""Memory HTTP operations use the same owner and enforce explicit review contracts."""
from fastapi.testclient import TestClient

from test_runtime_recovery import CountingProvider, app_for, finish, preview, selection


def test_memory_http_review_and_scope_contracts(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        assert client.get("/api/memory").json() == []
        assert client.get("/api/memory?unbounded=true").status_code == 422
        assert client.request("GET", "/api/memory", json={}).status_code == 422
        source = selection(client)
        unfinished = preview(client, source)
        excessive = [{"memoryId":f"memory-{index}", "version":1} for index in range(4)]
        assert client.post("/api/harness/preview", json={**source, "selectedMemory":excessive}).status_code == 422
        assert client.post("/api/memory/candidates", json={"runId":unfinished["runId"]}).status_code == 409
        initial, _, _ = finish(client, source)
        created = client.post("/api/memory/candidates", json={"runId":initial["runId"], "text":"Review evidence and unknown conditions."})
        assert created.status_code == 200, created.text
        candidate = created.json()
        assert candidate["status"] == "candidate" and candidate["general"] is False
        assert client.post("/api/memory/recommend", json={"runId":initial["runId"], "query":"conditions"}).json() == []
        assert client.post("/api/memory/candidates", json={"runId":initial["runId"], "scope":[]}).status_code == 422
        assert client.post("/api/memory/candidates", json={"runId":initial["runId"], "text":"x" * 4001}).status_code == 422
        path = f'/api/memory/{candidate["id"]}/promote'
        for reviewed in (False, 1, "true"):
            assert client.post(path, json={"version":1, "reviewed":reviewed, "note":"Review completed."}).status_code == 422
        active = client.post(path, json={"version":1, "reviewed":True, "note":"Synthetic scope and background reviewed."})
        assert active.status_code == 200, active.text
        item = active.json()
        assert item["status"] == "active" and item["version"] == 2
        duplicate = [{"memoryId":item["id"], "version":item["version"]}] * 2
        assert client.post("/api/harness/preview", json={**source, "selectedMemory":duplicate}).status_code == 409
        assert client.post("/api/memory/recommend", json={"runId":initial["runId"], "query":"conditions"}).json() == [item]
        assert client.post(path, json={"version":1, "reviewed":True, "note":"Stale review."}).status_code == 409
        history = client.get(f'/api/memory/{item["id"]}/versions').json()
        assert [record["status"] for record in history] == ["candidate", "active"]
        retired = client.post(f'/api/memory/{item["id"]}/retire', json={"version":2})
        assert retired.status_code == 200, retired.text
        assert retired.json()["version"] == 3 and retired.json()["status"] == "retired"
        assert client.post("/api/memory/recommend", json={"runId":initial["runId"], "query":"conditions"}).json() == []
        assert client.get("/api/memory/unknown/versions").status_code == 404
        assert provider.calls == ["context", "inference"]


def test_memory_http_conflict_resolution_requires_pair_version_review(tmp_path, source_root):
    with TestClient(app_for(tmp_path, source_root, CountingProvider()), raise_server_exceptions=False) as client:
        initial, _, _ = finish(client, selection(client))
        active = []
        for text in ("First conditions background.", "Second conditions background."):
            candidate = client.post("/api/memory/candidates", json={"runId":initial["runId"], "text":text}).json()
            active.append(client.post(f'/api/memory/{candidate["id"]}/promote', json={
                "version":candidate["version"], "reviewed":True, "note":"Reviewed synthetic conditions."}).json())
        ids = [item["id"] for item in active]
        conflicted = client.post("/api/memory/conflicts", json={"memoryIds":ids})
        assert conflicted.status_code == 200, conflicted.text
        assert all(item["conflicts"] for item in conflicted.json())
        payload = {"memoryIds":ids, "reviewed":True, "note":"Conditions apply to different cases."}
        assert client.post("/api/memory/resolve-conflict", json=payload).status_code == 422
        payload["versions"] = [{"memoryId":item["id"], "version":item["version"]} for item in active]
        assert client.post("/api/memory/resolve-conflict", json=payload).status_code == 409
        payload["versions"] = [{"memoryId":item["id"], "version":item["version"]} for item in conflicted.json()]
        resolved = client.post("/api/memory/resolve-conflict", json=payload)
        assert resolved.status_code == 200, resolved.text
        assert all(not item["conflicts"] for item in resolved.json())
