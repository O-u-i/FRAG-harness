"""User-visible connection operations, no real credentials or production installation."""
import json
from hashlib import sha256
from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from frag_api.fc_reader import install_fc
from frag_api.main import create_app


def test_prepare_connection_creates_private_template_once_without_returning_or_overwriting_secrets(tmp_path):
    state = tmp_path / 'state'; state.mkdir()
    with TestClient(create_app(state, 'x' * 64), headers={'Authorization': 'Bearer ' + 'x' * 64}) as api:
        first = api.post('/api/manage/fc-connection-prepare', json={})
        assert first.status_code == 200
        assert first.json() == {'created': True, 'readyToEdit': True}
        path = state / 'fc.env'
        assert path.is_file() and len(path.read_text().splitlines()) == 4
        secret = 'synthetic-reader-secret-do-not-return'
        content = ('FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788\n'
            'FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174\n'
            f'FINANCE_CORE_PLUGIN_READ_TOKEN={secret}\n'
            'FINANCE_CORE_PLUGIN_RECORDS_JSON={"synthetic":[]}\n')
        path.write_text(content)
        again = api.post('/api/manage/fc-connection-prepare', json={})
        assert again.status_code == 200 and again.json()['created'] is False
        assert path.read_text() == content and secret not in again.text
        assert api.post('/api/manage/fc-connection-prepare', json={'token': secret}).status_code == 403


@pytest.mark.parametrize('change', ['extra-key', 'duplicate-key', 'remote-url', 'two-vaults', 'duplicate-vault'])
def test_invalid_private_configuration_refuses_before_http_and_never_returns_file_or_secret(tmp_path, change, fc_archive, monkeypatch):
    state = tmp_path / 'state'; state.mkdir(); install_fc(fc_archive, state)
    with TestClient(create_app(state, 'x' * 64), headers={'Authorization': 'Bearer ' + 'x' * 64}) as api:
        assert api.post('/api/manage/fc-connection-prepare', json={}).status_code == 200
        content = ('FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788\nFINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174\n'
            'FINANCE_CORE_PLUGIN_READ_TOKEN=synthetic-secret-never-return\nFINANCE_CORE_PLUGIN_RECORDS_JSON={"synthetic":[]}\n')
        if change == 'extra-key': content += 'OPENAI_API_KEY=synthetic-unused-secret\n'
        if change == 'duplicate-key': content += 'FINANCE_CORE_PLUGIN_READ_TOKEN=synthetic-second-secret\n'
        if change == 'remote-url': content = content.replace('http://127.0.0.1:8788', 'https://example.com:8788')
        if change == 'two-vaults': content = content.replace('{"synthetic":[]}', '{"synthetic":[],"other":[]}')
        if change == 'duplicate-vault': content = content.replace('{"synthetic":[]}', '{"synthetic":[],"synthetic":[]}')
        (state / 'fc.env').write_text(content)
        calls = []
        def denied(request):
            calls.append(request.method)
            return httpx.Response(401, json={'error': {'code': 'AUTH_REQUIRED'}})
        real_client = httpx.Client
        monkeypatch.setattr(httpx, 'Client', lambda **options: real_client(**{**options, 'transport': httpx.MockTransport(denied)}))
        response = api.post('/api/manage/fc-connection-check', json={})
        assert response.status_code == 409
        assert calls == []
        assert 'synthetic-' not in response.text and str(state) not in response.text


@pytest.mark.parametrize('content', ['', 'synthetic-secret-in-nonprivate-file'])
def test_existing_nonprivate_file_is_not_silently_repaired_or_overwritten(tmp_path, content):
    state = tmp_path / 'state'; state.mkdir()
    path = state / 'fc.env'; path.write_text(content); path.chmod(0o644)
    with TestClient(create_app(state, 'x' * 64), headers={'Authorization': 'Bearer ' + 'x' * 64}) as api:
        response = api.post('/api/manage/fc-connection-prepare', json={})
        assert response.status_code == 409 and 'synthetic-secret' not in response.text
        assert path.read_text() == content


def test_check_and_human_selection_stay_inside_fc_grant_and_reconnect_disables_pending_delivery(tmp_path, fc_archive, monkeypatch):
    state = tmp_path / 'state'; state.mkdir(); install_fc(fc_archive, state)
    secret = 'synthetic-private-connection-secret'
    item_id = 'account:' + sha256(b'account\0cash').hexdigest()[:32]
    record = 'finance-item:' + item_id
    item = {'id': item_id, 'label': 'Living cash', 'kind': 'account', 'segment': 'living'}
    data = {'schemaVersion': 1, 'itemId': item_id, 'label': 'Living cash', 'kind': 'account', 'segment': 'living',
        'content': {'account': {'id': 'cash', 'name': 'Living cash', 'segment': 'living'},
                    'observations': [], 'postings': [], 'repayments': []},
        'coverage': {'selectionOnly': True, 'externalCompleteness': 'unknown', 'financialAdviceReady': False}}
    data['revision'] = sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    calls, available = [], [True]
    real_client = httpx.Client
    def serve(request):
        assert request.method == 'GET' and request.headers['authorization'] == 'Bearer ' + secret
        calls.append(request.url.path)
        if not available[0]:
            return httpx.Response(401, json={'error': {'code': 'AUTH_REQUIRED'}})
        path = request.url.path
        if path == '/api/v3/health':
            result = {'status': 'ok', 'service': 'finance-core', 'apiVersion': '3.10.0'}
        elif path == '/api/v3/access-token-self':
            result = {'data': {'actorKind': 'token', 'status': 'active', 'workspaceIds': ['synthetic'],
                'scopes': ['ledger:read'], 'readGrant': {'mode': 'living', 'itemIds': []}}}
        elif path == '/api/v3/workspaces':
            result = {'data': [{'id': 'synthetic', 'displayName': 'Synthetic sandbox', 'kind': 'sandbox', 'status': 'active'}]}
        elif path.endswith('/reader/catalog'):
            result = {'workspaceId': 'synthetic', 'readOnly': True,
                'data': {'schemaVersion': 1, 'readGrant': {'mode': 'living', 'itemIds': []}, 'items': [item]}}
        elif path.endswith('/reader/items/' + item_id):
            result = {'workspaceId': 'synthetic', 'readOnly': True, 'data': data}
        else:
            raise AssertionError('Unexpected official reader endpoint')
        return httpx.Response(200, json=result)
    monkeypatch.setattr(httpx, 'Client', lambda base_url, **options: real_client(base_url=base_url,
        **{**options, 'transport': httpx.MockTransport(serve)}))
    auth = {'Authorization': 'Bearer ' + 'x' * 64}
    with TestClient(create_app(state, 'x' * 64), headers=auth) as api:
        assert api.post('/api/manage/fc-connection-prepare', json={}).status_code == 200
        (state / 'fc.env').write_text('FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788\n'
            'FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174\n'
            f'FINANCE_CORE_PLUGIN_READ_TOKEN={secret}\nFINANCE_CORE_PLUGIN_RECORDS_JSON={{"synthetic":[]}}\n')
        checked = api.post('/api/manage/fc-connection-check', json={})
        assert checked.status_code == 200
        assert checked.json()['workspace']['kind'] == 'sandbox' and checked.json()['items'] == [item]
        assert not any('/reader/items/' in path or '/reports/' in path for path in calls)
        profile = {'id': 'finance-core', 'kind': 'fc', 'approved': True,
            'fcSelection': {'workspaceId': 'synthetic', 'recordIds': [record]}}
        invalid = {**profile, 'fcSelection': {'workspaceId': 'synthetic', 'recordIds': ['finance-item:account:' + 'a' * 32]}}
        assert api.post('/api/manage/source-save', json=invalid).status_code == 403
        saved = api.post('/api/manage/source-save', json=profile)
        assert saved.status_code == 200
        assert not any('/reader/items/' in path for path in calls)
        listing = api.post('/api/tools/frag_fc_read', json={'operation': 'list'}).json()
        assert listing['discovery']['scopes'][0]['records'] == [{'id': record, 'label': 'Living cash'}]
        payload = {'operation': 'read', 'workspaceId': 'synthetic', 'recordIds': [record]}
        pack = api.post('/api/tools/frag_fc_read', json=payload).json()
        assert pack['requiredEvidenceIds'] == [pack['evidence'][0]['evidenceId']]
        assert api.post('/api/tools/complete', json={'runId': pack['runId']}).status_code == 200
        pending = api.post('/api/tools/frag_fc_read', json=payload).json()
        path = state / 'fc.env'
        path.write_text(path.read_text().replace('5174', '5175'))
        assert api.post('/api/tools/complete', json={'runId': pending['runId']}).status_code == 409
        available[0] = False
        assert api.post('/api/manage/fc-connection-check', json={}).status_code == 409
        overview = api.post('/api/manage/overview', json={})
        assert overview.json()['sources'][0]['enabled'] is False
        assert api.post('/api/tools/complete', json={'runId': pending['runId']}).status_code != 200
        assert secret not in json.dumps([checked.json(), saved.json(), listing, pack, overview.json()])
    available[0] = True
    # Reconnection requires a new human authorization, including after restart.
    with TestClient(create_app(state, 'x' * 64), headers=auth) as api:
        assert api.post('/api/tools/frag_fc_read', json=payload).status_code == 403


@pytest.mark.parametrize('disabled', [False, True])
def test_first_host_start_prepares_bundled_pinned_reader_without_credentials_or_financial_reads(tmp_path, fc_archive, disabled):
    installation, project, state = (tmp_path / name for name in ('installation', 'project', 'state'))
    for path in (installation, project, state):
        path.mkdir()
    resources = installation / 'resources/finance-core'; resources.mkdir(parents=True)
    shutil.copyfile(fc_archive, resources / 'finance-core-frag-plugin-v1.10.0.zip')
    legacy = state / 'plugins/finance-core/versions/1.9.0/retained.txt'
    legacy.parent.mkdir(parents=True); legacy.write_text('Synthetic old version: retain for rollback.')
    pointer = state / 'plugins/finance-core/current.json'
    pointer.write_text(json.dumps({'enabled': not disabled, 'version': '1.9.0'}))
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0)); port = reserved.getsockname()[1]
    env = {**os.environ, 'FRAG_EXTENSION_TOKEN': 'x' * 64,
        'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-m', 'frag_api.host',
        '--installation', str(installation), '--workspace', str(project), '--state-dir', str(state), '--port', str(port)],
        cwd=installation, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', headers={'Authorization': 'Bearer ' + 'x' * 64}, trust_env=False) as api:
            for _ in range(100):
                assert process.poll() is None, 'Owned synthetic Host exited before health became ready.'
                try:
                    if api.get('/api/health', timeout=.3).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                pytest.fail('Owned synthetic Host did not become ready.')
            assert api.get('/api/health').json()['serviceVersion'] == '1.14.0'
            overview = api.post('/api/manage/overview', json={}).json()
            assert overview['runs'] == []
            assert overview['fcState'] == ('not_installed_or_disabled' if disabled else 'connection_required')
            assert legacy.read_text() == 'Synthetic old version: retain for rollback.'
            assert not (state / 'fc.env').exists()
            current = json.loads(pointer.read_text())
            assert current == {'enabled': False, 'version': '1.9.0'} if disabled else current == {'enabled': True, 'version': '1.10.0'}
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_duplicate_host_cannot_upgrade_reader_files_owned_by_a_running_backend(tmp_path, fc_archive):
    installation, project, state = (tmp_path / name for name in ('installation', 'project', 'state'))
    for path in (installation, project, state): path.mkdir()
    resources = installation / 'resources/finance-core'; resources.mkdir(parents=True)
    shutil.copyfile(fc_archive, resources / 'finance-core-frag-plugin-v1.10.0.zip')
    pointer = state / 'plugins/finance-core/current.json'; pointer.parent.mkdir(parents=True)
    original = json.dumps({'enabled': True, 'version': '1.9.0'})
    pointer.write_text(original)
    with TestClient(create_app(state, 'x' * 64), headers={'Authorization': 'Bearer ' + 'x' * 64}) as owner:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', 'frag_api.host', '--installation', str(installation),
            '--workspace', str(project), '--state-dir', str(state), '--port', '49152'], cwd=installation,
            env={**os.environ, 'FRAG_EXTENSION_TOKEN': 'x' * 64, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        assert result.returncode != 0
        assert pointer.read_text() == original
        assert owner.get('/api/health').status_code == 200
