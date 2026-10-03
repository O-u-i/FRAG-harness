"""Real tool routes bind selected snapshots and observations to the owning Run."""
from dataclasses import replace
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from frag_api.request_spec import fingerprint
from frag_api.schemas.tools import ToolCallRecord
from test_harness import selection


def selected(client):
    source = selection(client)
    preview = client.post('/api/harness/preview', json=source).json()
    binding = preview['sourceBindings'][0]
    arguments = {'identity':binding['identity'], 'revision':binding['revision'], 'locatorIds':binding['locatorIds'],
                 'evidenceIds':binding['evidenceIds']}
    return source, preview, arguments


def execute(client, source, preview, arguments, *, name='kb.read', call_id='selected-read'):
    return client.post(f"/api/runtime/runs/{preview['runId']}/tools/execute", json={
        'sourceRequest':source, 'call':{'callId':call_id, 'name':name, 'arguments':arguments}})


def test_registered_cli_read_and_native_search_are_actual_selected_operations(client):
    source, preview, args = selected(client)
    read = execute(client, source, preview, args)
    assert read.status_code == 200, read.text
    record = read.json()
    assert record['status'] == 'completed' and record['carrier'] == 'cli'
    assert record['result']['callId'] == 'selected-read'
    assert record['result']['evidence'] == preview['candidateEvidence']
    query = {key:value for key,value in args.items() if key != 'evidenceIds'}
    query.update(query='synthetic', limit=3)
    search = execute(client, source, preview, query, name='kb.search', call_id='native-search').json()
    assert search['status'] == 'completed' and search['carrier'] == 'native'
    assert search['result']['evidence']
    query['query'] = '不存在的词'
    missing = execute(client, source, preview, query, name='kb.search', call_id='no-match').json()
    assert missing['result']['evidence'] == [] and missing['result']['missingInformation']
    report = client.get(f"/api/runtime/runs/{preview['runId']}").json()
    assert [item['callId'] for item in report['toolCalls']] == ['selected-read','native-search','no-match']
    assert report['consumedTokens'] == 0 and report['requests'][0]['status'] == 'prepared'
    assert report['modelOutput'] is None and report['semanticReview'] == 'NOT_RUN'


@pytest.mark.parametrize('change', ['unknown', 'extra-path', 'missing', 'locator', 'revision', 'resource', 'namespace', 'fc', 'evidence'])
def test_invalid_or_unselected_arguments_do_not_execute_or_persist(client, change):
    source, preview, args = selected(client)
    name = 'kb.read'
    if change == 'unknown': name = 'shell.run'
    if change == 'extra-path': args['path'] = '../../outside.md'
    if change == 'missing': args.pop('evidenceIds')
    if change == 'locator': args['locatorIds'] = ['other-locator']
    if change == 'revision': args['revision'] = 'other-revision'
    if change == 'resource': args['identity']['resourceId'] = 'other-file'
    if change == 'namespace': args['identity']['namespace'] = 'other-root'
    if change == 'fc': args['identity'].update(kind='fc_record', workspaceId='other')
    if change == 'evidence': args['evidenceIds'] = ['not-selected']
    result = execute(client, source, preview, args, name=name)
    assert result.status_code in (409,422), result.text
    assert not client.get(f"/api/runtime/runs/{preview['runId']}").json()['toolCalls']


def test_source_reselection_cannot_read_a_different_file_or_plugin_before_validation(client, monkeypatch):
    source, preview, args = selected(client)
    service = client.app.state.harness_service
    monkeypatch.setattr(service.flow, 'prepare_preview', lambda *_: pytest.fail('Unselected source was read'))
    source['fileSelections'][0]['relativePath'] = '../outside.md'
    assert execute(client, source, preview, args).status_code == 409
    source['pluginSelection'] = {'workspaceId':'other', 'recordIds':['record']}
    assert execute(client, source, preview, args).status_code in (409,422)


def test_source_bytes_changed_after_preview_are_rejected(client, source_root):
    source, preview, args = selected(client)
    (source_root/'evidence.md').write_text('# Finding\nA changed claim.\n# Limits\nEvidence differs.',encoding='utf-8')
    assert execute(client, source, preview, args).status_code == 409


@pytest.mark.parametrize('change', ['call-id','content','missing-read','schema'])
def test_returned_result_must_match_call_and_selected_evidence(client, change):
    source, preview, args = selected(client)
    result = {'callId':'selected-read','evidence':preview['candidateEvidence'],'missingInformation':[]}
    if change == 'call-id': result['callId'] = 'other-call'
    if change == 'content': result['evidence'][0]['text'] = 'Invented text'
    if change == 'missing-read': result['evidence'] = []
    if change == 'schema': result['privateDebug'] = 'password=synthetic-secret'
    registry = client.app.state.kb_tools.registry
    registry._bindings['kb.read'] = replace(registry.get('kb.read'),execute=lambda _:result)
    response = execute(client, source, preview, args)
    assert response.status_code == 200
    assert response.json()['status'] == 'failed' and response.json()['errorCode'] == 'TOOL_RESULT_INVALID'
    assert 'synthetic-secret' not in response.text
    assert response.json()['callId'] == 'selected-read' and response.json()['result'] is None


def test_tool_calls_are_serial_deduplicated_and_bounded_with_durable_pause(client):
    source, preview, args = selected(client)
    query = {key:value for key,value in args.items() if key != 'evidenceIds'}
    query.update(query='synthetic', limit=3)
    tools = client.app.state.kb_tools
    original = tools.registry.get('kb.search')
    started, release = threading.Event(), threading.Event()
    def blocked(payload):
        started.set()
        assert release.wait(3)
        return original.execute(payload)
    tools.registry._bindings['kb.search'] = replace(original, execute=blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, client, source, preview, query, name='kb.search', call_id='one')
        assert started.wait(3)
        assert execute(client, source, preview, query, name='kb.search', call_id='two').status_code == 409
        # A model call cannot overlap an unresolved tool observation.
        rejected = client.post('/api/harness/run',json={**source,'contextFingerprint':preview['contextFingerprint'],
            'approvalToken':preview['approvalToken'],'approved':True})
        assert rejected.status_code == 409
        assert client.post(f"/api/runtime/runs/{preview['runId']}/review",json={
            'decision':'paused','target':'model','checklist':preview['task'],'note':'Pause during selected read'}).status_code == 200
        release.set()
        assert future.result().json()['status'] == 'completed'
    report = client.get(f"/api/runtime/runs/{preview['runId']}").json()
    assert report['run']['status'] == 'paused' and report['consumedTokens'] == 0
    assert report['toolCalls'][0]['callId'] == 'one'
    assert execute(client, source, preview, query, name='kb.search', call_id='three').status_code == 409


def test_call_id_replay_and_seventh_read_do_not_repeat_execution(client):
    source, preview, args = selected(client)
    assert execute(client, source, preview, args,call_id='one').json()['status'] == 'completed'
    assert execute(client, source, preview, args,call_id='one').status_code == 409
    for index in range(2,7):
        assert execute(client, source, preview, args,call_id=f'call{index}').json()['status'] == 'completed'
    assert execute(client, source, preview, args,call_id='seventh').status_code == 409
    assert len(client.get(f"/api/runtime/runs/{preview['runId']}").json()['toolCalls']) == 6


@pytest.mark.parametrize('value', ['active-token','sk-synthetic-privatekey'])
def test_executable_approval_or_secret_is_not_a_persisted_call_identifier(client, value):
    source, preview, args = selected(client)
    call_id = preview['approvalToken'] if value == 'active-token' else value
    result = execute(client, source, preview, args,call_id=call_id)
    assert result.status_code == 409 and result.json()['error']['code'] == 'POLICY_REJECTED'
    report = client.get(f"/api/runtime/runs/{preview['runId']}")
    assert call_id not in report.text and report.json()['toolCalls'] == []


def test_tool_interruption_becomes_unknown_without_automatic_retry(client):
    source, preview, args = selected(client)
    runtime = client.app.state.runtime
    pending = ToolCallRecord(callId='interrupted',name='kb.read',toolVersion='1.0.0',carrier='cli',
        arguments=args,status='dispatching',createdAt='2026-10-03T00:00:00Z')
    runtime.repository.update(preview['runId'],lambda record:record.tool_calls.append(pending))
    runtime.repository.recover_dispatches('2026-10-03T00:00:01Z')
    report = client.get(f"/api/runtime/runs/{preview['runId']}").json()
    assert report['run']['status'] == 'outcome_unknown'
    assert report['toolCalls'][0]['status'] == 'outcome_unknown'
    assert report['toolCalls'][0]['result'] is None and report['consumedTokens'] == 0
    assert execute(client, source, preview, args,call_id='new').status_code == 409
