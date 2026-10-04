"""Synthetic approvals drive actual KB tools and one model dispatch per request."""
import json
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmCallResult
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.research import ResearchDecision
from frag_api.services.runtime_service import RuntimeService
from test_harness import selection


def start(client, source=None):
    source = source or selection(client)
    response = client.post('/api/runtime/research/preview', json={'kind':'harness','sourceRequest':source})
    assert response.status_code == 200, response.text
    return source, response.json()


def preview(client, source, initial):
    response = client.post(f"/api/runtime/runs/{initial['runId']}/research/preview", json={'sourceRequest':source})
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, source, item):
    return client.post(f"/api/runtime/runs/{item['runId']}/research/execute", json={
        'sourceRequest':source,'fingerprint':item['fingerprint'],'approvalToken':item['approvalToken'],'approved':True})


class CaptureFake(FakeLlmProvider):
    def __init__(self): self.calls=[]
    def execute_prepared(self, call):
        self.calls.append(call)
        return super().execute_prepared(call)


def test_registered_research_runs_actual_cli_observation_then_formal_stages(client):
    model = CaptureFake()
    service = client.app.state.harness_service
    service.research_provider = service.context_provider = service.inference_provider = model
    source, first = start(client)
    body = json.loads(first['preparedCall']['body'])
    initial_input = json.loads(body['input'])
    assert initial_input['observations'] == [] and 'manifest' in initial_input
    assert 'A synthetic finding is supported.' not in body['input']
    assert body['max_output_tokens'] == 800 and len(model.calls) == 0
    catalog = client.get('/api/harness/capabilities').json()
    assert [row['name'] for row in catalog['loops']] == ['fixed','research'] and catalog['planned'] == []
    response = execute(client, source, first)
    assert response.status_code == 200, response.text
    one = response.json()
    assert len(model.calls) == 1 and len(one['toolCalls']) == 1
    assert one['toolCalls'][0]['carrier'] == 'cli' and one['toolCalls'][0]['status'] == 'completed'
    assert one['toolCalls'][0]['result']['callId'] == one['research']['turns'][0]['decision']['toolCalls'][0]['callId']
    assert one['context'] is None and 'approvalToken' not in response.text
    second = preview(client, source, first)
    assert len(model.calls) == 1 and second['approvalToken'] != first['approvalToken']
    next_input = json.loads(json.loads(second['preparedCall']['body'])['input'])
    assert 'A synthetic finding is supported.' in next_input['observations'][0]['result']['evidence'][0]['text']
    finish = execute(client, source, second)
    assert finish.status_code == 200, finish.text
    assert finish.json()['research']['status'] == 'awaiting_context' and len(model.calls) == 2
    context = preview(client, source, first)
    assert context['stage'] == 'context' and len(model.calls) == 2
    compressed = execute(client, source, context)
    assert compressed.status_code == 200, compressed.text
    assert compressed.json()['run']['status'] == 'awaiting_inference' and len(model.calls) == 3
    final_preview = preview(client, source, first)
    assert final_preview['stage'] == 'inference' and len(model.calls) == 3
    final = execute(client, source, final_preview)
    assert final.status_code == 200, final.text
    assert final.json()['run']['status'] == 'awaiting_review' and len(model.calls) == 4
    assert execute(client, source, final_preview).status_code == 409


def test_next_turn_requires_fresh_approval_and_tampering_is_rejected(client):
    source, first = start(client)
    tampered = dict(first, fingerprint='0'*64)
    assert execute(client, source, tampered).status_code == 409
    assert execute(client, source, first).status_code == 409  # Wrong-fingerprint consumes its token.
    renewed = preview(client, source, first)
    assert execute(client, source, renewed).status_code == 200
    assert execute(client, source, renewed).status_code == 409
    report = client.get(f"/api/runtime/runs/{first['runId']}").json()
    assert len([call for call in report['requests'] if call['status']=='completed']) == 1
    assert report['run']['activeCallId'] is None


@pytest.mark.parametrize('change', ['source','plugin','goal','task'])
def test_changed_selection_is_rejected_before_any_fresh_source_read(client, monkeypatch, change):
    source, first = start(client)
    monkeypatch.setattr(client.app.state.harness_service.flow, 'prepare_preview', lambda *_:pytest.fail('Unselected read'))
    if change=='source': source['fileSelections'][0]['relativePath']='../outside.md'
    if change=='plugin': source['pluginSelection']={'workspaceId':'other','recordIds':['one']}
    if change=='goal': source['goal']='Other goal'
    if change=='task': source['task']={'checklist':[{'id':'new','text':'New','blocking':False}]}
    assert execute(client, source, first).status_code in (409,422)


def test_source_or_tool_manifest_change_invalidates_preview(client, source_root):
    source, first = start(client)
    registry = client.app.state.kb_tools.registry
    old = registry.get('kb.search')
    registry._bindings['kb.search'] = replace(old,definition=old.definition.model_copy(update={'version':'1.0.1'}))
    assert execute(client,source,first).status_code == 409
    registry._bindings['kb.search']=old
    (source_root/'evidence.md').write_text('# Finding\nChanged source.',encoding='utf-8')
    assert execute(client,source,first).status_code == 409


@pytest.mark.parametrize('invalid', ['unknown','incomplete','duplicate','unselected','partial','foreign-finish','secret-id', 'extra-auth', 'token-key'])
def test_invalid_complete_proposals_never_execute_tools(client, invalid):
    source, first = start(client)
    original = FakeLlmProvider()
    class Invalid:
        def execute_prepared(self, call):
            value = original.execute_prepared(call).output.model_dump(by_alias=True)
            if invalid=='unknown': value['toolCalls'][0]['name']='shell.run'
            if invalid=='incomplete': value['toolCalls'][0]['arguments'].pop('evidenceIds')
            if invalid=='duplicate': value['toolCalls']*=2
            if invalid=='unselected': value['toolCalls'][0]['arguments']['locatorIds']=['other']
            if invalid=='partial': value['toolCalls'][0]['arguments']='{"evidenceIds":'
            if invalid=='foreign-finish': value.update(action='finish',toolCalls=[],evidenceIds=['foreign'])
            if invalid=='secret-id': value['toolCalls'][0]['callId']='sk-synthetic-privatekey'
            if invalid=='extra-auth':value['toolCalls'][0]['arguments']['authorization']=first['approvalToken']
            if invalid=='token-key':value['toolCalls'][0]['arguments'][first['approvalToken']]='malformed'
            return LlmCallResult(SimpleNamespace(model_dump=lambda **_:value),ProviderUsage(inputTokens=1,outputTokens=1))
    # raw dict models simulate transport output before typed validation without permissive production parsing.
    class Raw:
        def execute_prepared(self,call):
            result=Invalid().execute_prepared(call)
            return LlmCallResult(result.output.model_dump(),result.usage)
    client.app.state.harness_service.research_provider=Raw()
    response=execute(client,source,first)
    assert response.status_code==502, response.text
    report=client.get(f"/api/runtime/runs/{first['runId']}").json()
    assert report['toolCalls']==[] and report['run']['status']=='error'
    assert report['research']['turns'][0]['status']=='failed'
    assert 'synthetic-privatekey' not in json.dumps(report)
    assert first['approvalToken'] not in json.dumps(report)


def test_three_continue_turns_stop_without_fourth_model_dispatch(client):
    class ContinueFake(FakeLlmProvider):
        calls=0
        def execute_prepared(self,call):
            self.calls+=1
            payload=call.request_body_input(); binding=payload['manifest'][0]
            return LlmCallResult(ResearchDecision(action='continue',toolCalls=[{'callId':f"search-{self.calls}",
                'name':'kb.search','arguments':{'identity':binding['identity'],'revision':binding['revision'],
                    'locatorIds':binding['locatorIds'],'query':'absentword','limit':3}}],evidenceIds=[],missingInformation=['No matching selected evidence.']),
                ProviderUsage(inputTokens=1,outputTokens=1))
    model=ContinueFake();client.app.state.harness_service.research_provider=model
    source,current=start(client)
    for index in range(3):
        result=execute(client,source,current);assert result.status_code==200,result.text
        if index<2: current=preview(client,source,current)
    assert result.json()['research']['status']=='exhausted' and model.calls==3
    assert len(result.json()['toolCalls'])==3
    assert client.post(f"/api/runtime/runs/{current['runId']}/research/preview",json={'sourceRequest':source}).status_code==409


def test_unknown_model_outcome_never_resends_after_restart(client):
    class Unknown:
        def execute_prepared(self,call): raise TimeoutError('Do not expose endpoint or secret')
    client.app.state.harness_service.research_provider=Unknown()
    source,first=start(client)
    assert execute(client,source,first).status_code==502
    saved=client.get(f"/api/runtime/runs/{first['runId']}").json()
    assert saved['run']['status']=='outcome_unknown'
    assert saved['research']['status']=='outcome_unknown'
    RuntimeService(client.app.state.runtime.repository)
    assert client.post(f"/api/runtime/runs/{first['runId']}/research/preview",json={'sourceRequest':source}).status_code==409
