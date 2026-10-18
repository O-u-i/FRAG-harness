"""Slice B development cases at the existing private HTTP tool/management seam."""
from fastapi.testclient import TestClient
import pytest
import subprocess
import sys
from zipfile import ZipFile

from frag_api.main import create_app


def test_human_confirmed_plan_is_a_whole_required_document_not_a_read_window(tmp_path):
    root = tmp_path / 'approved'
    root.mkdir()
    content = '---\nstatus: synthetic-test-only\n---\n# Funding plan\nSynthetic tuition target.\n' + 'Complete constraint.\n' * 450 + '\n## Counterevidence\nDo not assume future income.\n'
    (root / 'plan.md').write_bytes(content.encode('utf8'))
    with TestClient(create_app(tmp_path / 'state', 'x' * 64)) as api:
        api.headers['authorization'] = 'Bearer ' + 'x' * 64
        assert api.post('/api/manage/source-save', json={'id': 'kb', 'root': str(root), 'approved': True}).status_code == 200
        assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
        def search():
            pack = api.post('/api/tools/frag_search', json={'query': 'tuition target'}).json()
            assert api.post('/api/tools/complete', json={'runId': pack['runId']}).status_code == 200
            return pack
        found = search()
        key = found['evidence'][0]['evidenceId']
        confirmation = api.post('/api/manage/plan-confirm', json={'runId': found['runId'], 'evidenceId': key, 'confirmed': True})
        assert confirmation.status_code == 200
        found = search()  # Human authorization advances the source revision.
        pack = api.post('/api/tools/frag_read', json={'searchRunId': found['runId'], 'evidenceIds': [found['evidence'][0]['evidenceId']], 'requireCompletePlan': True})
        assert pack.status_code == 200
        value = pack.json()
        item = value['evidence'][0]
        assert item['text'] == content
        assert item['windowed'] is False and item['role'] == 'confirmed_plan'
        assert value['requiredEvidenceIds'] == [item['evidenceId']]
        assert api.post('/api/tools/complete', json={'runId': value['runId'], 'omittedEvidenceIds': [item['evidenceId']]}).status_code == 403


@pytest.fixture
def plan_case(tmp_path):
    root = tmp_path / 'approved'
    root.mkdir()
    path = root / 'plan.md'
    path.write_bytes(b'# Synthetic plan\nTuition target and independent funding constraints.\n')
    with TestClient(create_app(tmp_path / 'state', 'x' * 64)) as api:
        api.headers['authorization'] = 'Bearer ' + 'x' * 64
        assert api.post('/api/manage/source-save', json={'id': 'kb', 'root': str(root), 'approved': True}).status_code == 200
        assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
        yield api, path


def found_plan(api):
    pack = api.post('/api/tools/frag_search', json={'query': 'tuition target', 'topK': 10}).json()
    assert api.post('/api/tools/complete', json={'runId': pack['runId']}).status_code == 200
    return pack


def confirm(api, pack):
    return api.post('/api/manage/plan-confirm', json={'runId': pack['runId'], 'evidenceId': pack['evidence'][0]['evidenceId'], 'confirmed': True})


def read_plan(api, pack):
    return api.post('/api/tools/frag_read', json={'searchRunId': pack['runId'], 'evidenceIds': [item['evidenceId'] for item in pack['evidence']], 'requireCompletePlan': True})


def test_a_file_hit_is_not_confirmation_and_tools_cannot_authorize_a_plan(plan_case):
    api, _ = plan_case
    found = found_plan(api)
    assert read_plan(api, found).status_code == 403
    assert api.post('/api/tools/plan-confirm', json={'runId': found['runId'], 'evidenceId': found['evidence'][0]['evidenceId'], 'confirmed': True}).status_code == 404
    for value in (False, 1, 'true'):
        assert api.post('/api/manage/plan-confirm', json={'runId': found['runId'], 'evidenceId': found['evidence'][0]['evidenceId'], 'confirmed': value}).status_code == 422
    assert api.post('/api/manage/plan-confirm', json={'runId': found['runId'], 'evidenceId': '0' * 24, 'confirmed': True}).status_code == 403
    ordinary = api.post('/api/tools/frag_read', json={'searchRunId': found['runId'], 'evidenceIds': [found['evidence'][0]['evidenceId']]})
    assert ordinary.status_code == 200 and ordinary.json()['requiredEvidenceIds'] == []


def test_refreshing_changed_material_does_not_reconfirm_a_plan(plan_case):
    api, path = plan_case
    assert confirm(api, found_plan(api)).status_code == 200
    pending = read_plan(api, found_plan(api)).json()
    path.write_bytes(b'# Revised synthetic plan\nTuition target now has different constraints.\n')
    assert api.post('/api/tools/complete', json={'runId': pending['runId']}).status_code == 409
    assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
    refreshed = found_plan(api)
    assert read_plan(api, refreshed).status_code == 403
    assert confirm(api, refreshed).status_code == 200
    assert read_plan(api, found_plan(api)).status_code == 200


def test_complete_plan_overflow_refuses_instead_of_returning_a_window(plan_case):
    api, path = plan_case
    path.write_bytes(b'# Synthetic plan\nTuition target.\n' + b'Full constraint.\n' * 1200)
    assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
    assert confirm(api, found_plan(api)).status_code == 200
    response = read_plan(api, found_plan(api))
    assert response.status_code == 403
    assert response.json() == {'error': {'code': 'POLICY_REJECTED'}}
    overview = api.post('/api/manage/overview', json={}).json()
    assert overview['runs'][0]['status'] == 'failed' and overview['runs'][0]['pack'] is None


def test_whole_plan_and_selected_memory_are_both_retained_or_refused(plan_case):
    api, path = plan_case
    path.write_bytes(b'# Synthetic plan\nTuition target.\n' + b'Critical limit.\n' * 660)
    assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
    assert confirm(api, found_plan(api)).status_code == 200
    found = found_plan(api)
    selections = []
    for index in range(3):
        candidate = api.post('/api/manage/memory-candidate', json={'runId': found['runId'], 'text': 'Synthetic background. ' * 140, 'general': True}).json()
        active = api.post('/api/manage/memory-promote', json={'memoryId': candidate['id'], 'version': 1, 'reviewed': True, 'note': 'Synthetic reviewed background'}).json()
        selections.append({'memoryId': active['id'], 'version': active['version']})
    profile = api.post('/api/manage/overview', json={}).json()['sources'][0]
    profile['selectedMemory'] = selections
    assert api.post('/api/manage/source-save', json=profile).status_code == 200
    assert read_plan(api, found_plan(api)).status_code == 403
    profile = api.post('/api/manage/overview', json={}).json()['sources'][0]
    profile['selectedMemory'] = selections[:1]
    assert api.post('/api/manage/source-save', json=profile).status_code == 200
    pack = read_plan(api, found_plan(api)).json()
    assert pack['memoryBackground'][0]['memoryId'] == selections[0]['memoryId']
    assert len(pack['evidence'][0]['text']) > 8000
    assert pack['budget']['omittedEvidenceIds'] == []


def test_multiple_section_hits_deduplicate_to_one_whole_plan(plan_case):
    api, path = plan_case
    content = b'# Tuition target\nSynthetic main plan.\n## Tuition target constraints\nKeep the independent limit.\n'
    path.write_bytes(content)
    assert api.post('/api/manage/source-build', json={'sourceId': 'kb'}).status_code == 200
    found = found_plan(api)
    assert len(found['evidence']) == 2
    assert confirm(api, found).status_code == 200
    pack = read_plan(api, found_plan(api)).json()
    assert len(pack['evidence']) == 1
    assert pack['evidence'][0]['text'] == content.decode()
    assert pack['requiredEvidenceIds'] == [pack['evidence'][0]['evidenceId']]


def test_clearing_plan_authorization_preserves_files_and_completed_history(plan_case):
    api, path = plan_case
    assert confirm(api, found_plan(api)).status_code == 200
    pack = read_plan(api, found_plan(api)).json()
    assert api.post('/api/tools/complete', json={'runId': pack['runId']}).status_code == 200
    before = path.read_bytes()
    profile = api.post('/api/manage/overview', json={}).json()['sources'][0]
    profile['confirmedPlans'] = []
    assert api.post('/api/manage/source-save', json=profile).status_code == 200
    assert read_plan(api, found_plan(api)).status_code == 403
    assert path.read_bytes() == before
    saved = api.post('/api/manage/run-get', json={'runId': pack['runId']}).json()
    assert saved['status'] == 'completed' and saved['pack'] == pack


def test_disabled_plan_configuration_and_completed_runs_remain_readable_by_retained_host(plan_case, tmp_path, request):
    archive = request.config.getoption('--legacy-host')
    if not archive:
        pytest.skip('Retained matching Host not supplied; no installation is attempted.')
    api, path = plan_case
    assert confirm(api, found_plan(api)).status_code == 200
    pack = read_plan(api, found_plan(api)).json()
    assert api.post('/api/tools/complete', json={'runId': pack['runId']}).status_code == 200
    profile = api.post('/api/manage/overview', json={}).json()['sources'][0]
    profile['confirmedPlans'] = []
    assert api.post('/api/manage/source-save', json=profile).status_code == 200
    legacy = tmp_path / 'retained-host'
    with ZipFile(archive) as source:
        assert source.read('backend/frag_api/main.py').find(b'VERSION = "1.13.0"') >= 0
        for name in source.namelist():
            if name.startswith('backend/frag_api/') and name.endswith('.py'):
                target = (legacy / name).resolve()
                assert target.is_relative_to(legacy.resolve())
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(name))
    api.app.state.tools.repository.close()  # Stop current owner before opening retained backend.
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from frag_api.main import create_app
with TestClient(create_app(Path(sys.argv[2]), 'x'*64)) as api:
    api.headers['authorization']='Bearer '+'x'*64
    assert api.get('/api/health').json()['serviceVersion']=='1.13.0'
    assert api.post('/api/manage/overview', json={}).status_code==200
    assert api.post('/api/manage/run-get', json={'runId':sys.argv[3]}).json()['status']=='completed'
    found=api.post('/api/tools/frag_search', json={'query':'tuition target'}).json()
    assert api.post('/api/tools/complete', json={'runId':found['runId']}).status_code==200
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', script, str(legacy / 'backend'), str(tmp_path / 'state'), pack['runId']], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert path.is_file()
