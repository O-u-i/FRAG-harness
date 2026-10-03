"""Human review changes cannot be weakened by restoring the older input checklist."""
import copy
import pytest
from fastapi.testclient import TestClient


def task():
    return {"templateId":"evidence-review-v1", "checklist":[{"id":"facts", "text":"Confirm the selected finding",
            "blocking":True, "status":"met", "reviewed":True}]}


def source(client):
    inspected = client.post('/api/context-sources/files/inspect', json={"relativePath":"evidence.md"}).json()
    return {"goal":"Review the selected finding", "fileSelections":[{"relativePath":"evidence.md",
        "locatorIds":[inspected['locators'][0]['id']], "relevanceReason":"Selected for review"}], "task":task()}


def test_changed_blocking_review_stays_paused_on_fresh_resume(client: TestClient):
    selected = source(client)
    preview = client.post('/api/harness/preview', json=selected).json()
    url = f"/api/runtime/runs/{preview['runId']}"
    unknown = copy.deepcopy(task())
    unknown['checklist'][0].update(status='unknown', reviewed=False)
    paused = client.post(url+'/review', json={"decision":"paused", "checklist":unknown})
    assert paused.status_code == 200
    recovered = client.post(url+'/resume/preview', json={"sourceRequest":selected})
    assert recovered.status_code == 409 and recovered.json()['error']['code'] == 'POLICY_REJECTED'
    assert client.get(url).json()['run']['status'] == 'paused'
    assert len(client.get(url).json()['requests']) == 1
    ready = client.post(url+'/review', json={"decision":"paused", "checklist":task()})
    assert ready.status_code == 200
    assert client.post(url+'/resume/preview', json={"sourceRequest":selected}).status_code == 200


def test_checklist_review_requires_boolean_values(client: TestClient):
    selected = source(client)
    selected['task']['checklist'][0]['reviewed'] = 'true'
    assert client.post('/api/harness/preview', json=selected).status_code == 422
    selected['task']['checklist'][0]['reviewed'] = 1
    assert client.post('/api/harness/preview', json=selected).status_code == 422


def test_active_approval_value_is_redacted_from_new_snapshots(client: TestClient):
    selected = source(client)
    first = client.post('/api/harness/preview', json=selected).json()
    token = first['approvalToken']
    selected['goal'] += ' ' + token
    response = client.post('/api/harness/preview', json=selected)
    assert response.status_code == 200
    second = response.json()
    assert token not in response.text
    stored = client.get(f"/api/runtime/runs/{second['runId']}")
    assert token not in stored.text and 'approvalToken' not in stored.text
    assert second['preparedCall']['fingerprint'] == second['contextFingerprint']
    executed = client.post('/api/harness/run', json={**selected, 'contextFingerprint':second['contextFingerprint'],
        'approvalToken':second['approvalToken'], 'approved':True})
    assert executed.status_code == 200, executed.text
    assert token not in executed.text


def test_checkpoint_digests_bind_redacted_content(client: TestClient):
    from frag_api.request_spec import fingerprint
    selected = source(client)
    preview = client.post('/api/harness/preview', json=selected).json()
    ran = client.post('/api/harness/run', json={**selected, 'contextFingerprint':preview['contextFingerprint'],
        'approvalToken':preview['approvalToken'], 'approved':True})
    assert ran.status_code == 200
    run_id = preview['runId']
    report = client.get(f'/api/runtime/runs/{run_id}').json()
    assert report['snapshotDigest'] == fingerprint(report['selection'])
    returned = next(c for c in report['requests'] if c['status'] == 'completed')
    assert returned['outputDigest'] == fingerprint(returned['output'])
    def corrupt_snapshot(record):
        record.selection.goal = 'Corrupted snapshot'
    client.app.state.runtime.repository.update(run_id, corrupt_snapshot)
    recovered = client.post(f'/api/runtime/runs/{run_id}/resume/preview', json={'sourceRequest':selected})
    assert recovered.status_code == 409


def test_runtime_database_cannot_share_the_rag_index(tmp_path, source_root):
    from frag_api.main import create_app
    path = tmp_path / 'shared.sqlite3'
    app = create_app(context_source_root=source_root, rag_index_path=path, runtime_path=path, plugin_root=tmp_path/'plugins')
    with pytest.raises(ValueError, match='separate from the RAG index'):
        with TestClient(app):
            pass
