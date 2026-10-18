import json
import httpx
import pytest
from fastapi.testclient import TestClient
from frag_api.fc_reader import install_fc, load_fc, _checked_package
from frag_api.main import create_app
from frag_api.errors import PluginValidationError, PolicyRejectedError, RuntimeConflictError
from frag_api.repositories.tool_store import ToolStore
from frag_api.schemas.native import SourceProfile, FcInput, CompleteInput
from frag_api.services.evidence_tools import EvidenceTools


def test_fc_package_is_named_and_byte_pinned(tmp_path, fc_archive, monkeypatch):
    state = tmp_path/'state'; state.mkdir()
    install_fc(fc_archive,state)
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN','synthetic-token')
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_RECORDS_JSON','{"synthetic":["entry:one"]}')
    reader = load_fc(state/'plugins')
    assert reader.version == '1.10.0'
    assert reader.id == 'finance-core'
    with pytest.raises(PluginValidationError):
        _checked_package(state/'plugins','untrusted-other')
    (reader.directory/'ui.js').write_text('altered package')
    with pytest.raises(PluginValidationError):
        reader.ensure_current()
    with pytest.raises(PluginValidationError):
        install_fc(fc_archive,state)


def test_fc_tools_use_only_whitelisted_http_get_and_revalidate(tmp_path,fc_archive,monkeypatch):
    state = tmp_path/'state'; state.mkdir(); install_fc(fc_archive,state)
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN','synthetic-token')
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_RECORDS_JSON','{"synthetic":["entry:one"]}')
    reader = load_fc(state/'plugins')
    calls=[]; value={'description':'Synthetic record','id':'one','value':'1'}
    def serve(request):
        calls.append((request.method,request.url.path))
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        if request.url.path == '/api/v3/health':
            result={'status':'ok','service':'finance-core','apiVersion':'3.10.0'}
        elif request.url.path == '/api/v3/workspaces':
            result={'data':[{'id':'synthetic','status':'active','name':'Synthetic Workspace'}]}
        elif request.url.path == '/api/v3/workspaces/synthetic/journal-entries/one':
            result={'workspaceId':'synthetic','data':value}
        else:
            raise AssertionError('Unexpected endpoint')
        return httpx.Response(200,json=result)
    monkeypatch.setitem(reader.read_evidence.__globals__,'_client',lambda base,token:httpx.Client(base_url=base,headers={'authorization':'Bearer '+token},transport=httpx.MockTransport(serve)))
    store=ToolStore(state/'runtime.sqlite3'); tools=EvidenceTools(store,state/'indexes',reader)
    try:
        store.save_profile(SourceProfile(id='finance-core',kind='fc',approved=True))
        discovery=tools.fc_read(FcInput(operation='list'))
        assert tools.complete(CompleteInput(runId=discovery['runId']))['discovery']['scopes'][0]['id']=='synthetic'
        with pytest.raises(PolicyRejectedError):
            tools.fc_read(FcInput(operation='read',workspaceId='outside',recordIds=['entry:one']))
        pack=tools.fc_read(FcInput(operation='read',workspaceId='synthetic',recordIds=['entry:one']))
        final=tools.complete(CompleteInput(runId=pack['runId']))
        assert len(final['evidence'])==1 and 'synthetic-token' not in json.dumps(final)
        pending=tools.fc_read(FcInput(operation='read',workspaceId='synthetic',recordIds=['entry:one']))
        value['value']='2'
        with pytest.raises(RuntimeConflictError):
            tools.complete(CompleteInput(runId=pending['runId']))
        assert all(method=='GET' for method,_ in calls)
        monkeypatch.setenv('FINANCE_CORE_PLUGIN_RECORDS_JSON','{}')
        with pytest.raises(PluginValidationError):
            reader.ensure_current()
    finally:
        store.close()


def test_month_to_date_official_reader_completes_whole_native_run_and_refuses_changed_or_oversized_reports(tmp_path, fc_archive, monkeypatch):
    state = tmp_path / 'state'
    state.mkdir()
    install_fc(fc_archive, state)
    record = 'month-to-date:2026-08-18'
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_READ_TOKEN', 'synthetic-read-token')
    monkeypatch.setenv('FINANCE_CORE_PLUGIN_RECORDS_JSON', json.dumps({'synthetic': [record]}))
    row = {'commodityCode': 'CNY', 'cashInflow': '12.34', 'cashOutflow': '0', 'cashNet': '12.34',
        'income': '12.34', 'expenses': '0', 'netIncome': '12.34', 'cashAdjustment': '0',
        'incomeAdjustment': '0', 'expenseAdjustment': '0', 'cashNetChange': None, 'incomeChange': None, 'expensesChange': None}
    report = {'schemaVersion': 1, 'calculationVersion': 'month-to-date-v1', 'month': '2026-08',
        'asOf': '2026-08-18', 'windowStart': '2026-08-01', 'windowEndExclusive': '2026-08-19',
        'periodStatus': 'partial', 'status': 'ready', 'revision': 'a' * 64,
        'period': {'month': '2026-08', 'postedEntryCount': 1, 'reversalEntryCount': 0,
                   'otherCategoryPostingCount': 2, 'currencies': [row]},
        'coverage': {'ledgerCalculation': 'complete', 'externalCompleteness': 'unknown',
                     'accountClassification': 'current-account-definitions', 'invalidDateEntryCount': 0,
                     'activityBasis': 'posted-journal-only', 'unrecordedDays': 'unknown'}}
    calls = []
    def serve(request):
        assert request.method == 'GET'
        assert request.headers['authorization'] == 'Bearer synthetic-read-token'
        calls.append(request.url.raw_path.decode())
        if request.url.path == '/api/v3/health':
            result = {'status': 'ok', 'service': 'finance-core', 'apiVersion': '3.10.0'}
        elif request.url.path == '/api/v3/workspaces':
            result = {'data': [{'id': 'synthetic', 'status': 'active', 'displayName': 'Synthetic'}]}
        elif request.url.path == '/api/v3/workspaces/synthetic/reports/month-to-date':
            assert dict(request.url.params) == {'asOf': '2026-08-18'}
            result = {'workspaceId': 'synthetic', 'readOnly': True, 'data': report}
        else:
            raise AssertionError('Unexpected reader endpoint')
        return httpx.Response(200, json=result)
    app = create_app(state, 'x' * 64)
    reader = app.state.tools.fc
    monkeypatch.setitem(reader.read_evidence.__globals__, '_client', lambda base, token: httpx.Client(
        base_url=base, headers={'Authorization': 'Bearer ' + token}, transport=httpx.MockTransport(serve)))
    with TestClient(app, headers={'Authorization': 'Bearer ' + 'x' * 64}) as api:
        assert api.post('/api/manage/source-save', json={'id': 'finance-core', 'kind': 'fc', 'approved': True}).status_code == 200
        listing = api.post('/api/tools/frag_fc_read', json={'operation': 'list'})
        assert listing.status_code == 200
        assert not any('/reports/' in path for path in calls)
        assert api.post('/api/tools/complete', json={'runId': listing.json()['runId']}).status_code == 200
        payload = {'operation': 'read', 'workspaceId': 'synthetic', 'recordIds': [record]}
        pack = api.post('/api/tools/frag_fc_read', json=payload).json()
        assert pack['requiredEvidenceIds'] == [pack['evidence'][0]['evidenceId']]
        result = api.post('/api/tools/complete', json={'runId': pack['runId']})
        assert result.status_code == 200
        assert json.loads(result.json()['evidence'][0]['text'].split('\n', 1)[1]) == report
        saved = api.post('/api/manage/run-get', json={'runId': pack['runId']}).json()
        assert saved['status'] == 'completed'
        assert 'synthetic-read-token' not in json.dumps(saved)
        pending = api.post('/api/tools/frag_fc_read', json=payload).json()
        report['revision'] = 'b' * 64
        refused = api.post('/api/tools/complete', json={'runId': pending['runId']})
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'REVISION_CONFLICT'
        failed = api.post('/api/manage/run-get', json={'runId': pending['runId']}).json()
        assert failed['status'] == 'failed' and failed['pack'] is None
        report['period']['currencies'] = [{**row, 'commodityCode': f'C{i:02d}'} for i in range(64)]
        too_large = api.post('/api/tools/frag_fc_read', json=payload)
        assert too_large.status_code == 403 and too_large.json()['error']['code'] == 'POLICY_REJECTED'
        assert api.post('/api/manage/run-get', json={'runId': pack['runId']}).json() == saved
