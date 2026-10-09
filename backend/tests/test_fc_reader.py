import json
import httpx
import pytest
from frag_api.fc_reader import install_fc, load_fc, _checked_package
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
    assert reader.version == '1.1.0'
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
            result={'status':'ok','service':'finance-core','apiVersion':'3.1.1'}
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
