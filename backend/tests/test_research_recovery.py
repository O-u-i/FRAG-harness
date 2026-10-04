"""Reliable research checkpoints, bounded proposals and human control survive restarts."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmCallResult
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.research import ResearchDecision
from frag_api.services.runtime_service import now
from test_research_loop import start, preview, execute


def two_sources(client):
    inspected=client.post('/api/context-sources/files/inspect',json={'relativePath':'evidence.md'}).json()
    return {'goal':'Explain selected evidence','fileSelections':[{'relativePath':'evidence.md',
        'locatorIds':[row['id'] for row in inspected['locators']],'relevanceReason':'Selected synthetic sections'}]}


class FirstOnly(FakeLlmProvider):
    def execute_prepared(self,call):
        result=super().execute_prepared(call)
        if call.purpose=='research' and result.output.action=='continue':
            result.output.tool_calls[0]=result.output.tool_calls[0].model_copy(deep=True,update={
                'arguments':{**result.output.tool_calls[0].arguments,'evidenceIds':result.output.tool_calls[0].arguments['evidenceIds'][:1]}})
        if call.purpose=='research' and result.output.action=='finish':
            result.output.missing_information=['The unobserved second section remains unknown.']
        return result


def test_formal_context_contains_only_observed_finish_subset_and_preserves_missing(client):
    service=client.app.state.harness_service;service.research_provider=FirstOnly()
    source,initial=start(client,two_sources(client))
    assert execute(client,source,initial).status_code==200
    second=preview(client,source,initial)
    done=execute(client,source,second).json()
    assert len(done['selection']['candidateEvidence'])==2
    assert len(done['research']['selectedEvidenceIds'])==1
    formal=preview(client,source,initial)
    wire=json.loads(json.loads(formal['preparedCall']['body'])['input'])
    assert len(wire['evidence'])==1 and 'Evidence is incomplete.' not in json.dumps(wire)
    assert wire['researchMissingInformation']==done['research']['missingInformation']
    context=execute(client,source,formal)
    assert context.status_code==200,context.text
    assert context.json()['context']['missingInformation']==done['research']['missingInformation']
    inference=preview(client,source,initial)
    final=execute(client,source,inference)
    assert final.status_code==200,final.text
    assert final.json()['modelOutput']['missingInformation']==done['research']['missingInformation']


@pytest.mark.parametrize('mutation',['version','carrier','scope','missing-read','duplicate-result','duplicate-record','selected-finish','context'])
def test_mutated_saved_trajectory_rejected_before_fresh_reads(client,monkeypatch,mutation):
    client.app.state.harness_service.research_provider=FirstOnly()
    source,initial=start(client,two_sources(client))
    assert execute(client,source,initial).status_code==200
    runtime=client.app.state.runtime
    if mutation in ('selected-finish','context'):
        assert execute(client,source,preview(client,source,initial)).status_code==200
    if mutation=='context':
        assert execute(client,source,preview(client,source,initial)).status_code==200
    def damage(report):
        tool=report.tool_calls[0]
        if mutation=='version':tool.tool_version='9.9.9'
        if mutation=='carrier':tool.carrier='native'
        if mutation=='scope':tool.result.evidence.append(report.selection.candidate_evidence[1])
        if mutation=='missing-read':tool.result.evidence=[]
        if mutation=='duplicate-result':tool.result.evidence*=2
        if mutation=='duplicate-record':report.tool_calls.append(tool.model_copy(deep=True))
        if mutation=='selected-finish':report.research.selected_evidence_ids.append(report.selection.candidate_evidence[1].evidence_id)
        if mutation=='context':report.context.evidence[0].summary='Forged retained context'
    runtime.repository.update(initial['runId'],damage)
    monkeypatch.setattr(client.app.state.harness_service.flow,'prepare_preview',lambda *_:pytest.fail('Corrupt history reread source'))
    response=client.post(f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
    assert response.status_code==409,response.text


def test_two_concurrent_previews_keep_active_attempt_and_pending_turn_atomic(client,monkeypatch):
    source,initial=start(client)
    runtime=client.app.state.runtime;original=runtime.prepare
    gate=threading.Barrier(2)
    def concurrent(*args,**kwargs):
        gate.wait(timeout=3)
        return original(*args,**kwargs)
    monkeypatch.setattr(runtime,'prepare',concurrent)
    def request():return client.post(f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=[item.result() for item in [pool.submit(request),pool.submit(request)]]
    assert sorted(item.status_code for item in responses)==[200,409]
    saved=runtime.repository.get(initial['runId'])
    pending=next(turn for turn in saved.research.turns if turn.status=='model_pending')
    assert saved.run.active_call_id==pending.attempt_id
    assert execute(client,source,next(item.json() for item in responses if item.status_code==200)).status_code==200


def test_human_pause_during_real_tool_preserved_and_explicit_resume_does_not_repeat(client):
    source,initial=start(client)
    original=client.app.state.kb_tools.registry.get('kb.read')
    entered,release=threading.Event(),threading.Event()
    def blocked(payload):
        entered.set();assert release.wait(3);return original.execute(payload)
    client.app.state.kb_tools.registry._bindings['kb.read']=replace(original,execute=blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        call=pool.submit(execute,client,source,initial)
        assert entered.wait(3)
        saved=client.app.state.runtime.repository.get(initial['runId'])
        paused=client.post(f"/api/runtime/runs/{initial['runId']}/review",json={'decision':'paused',
            'checklist':saved.selection.task.model_dump(by_alias=True),'note':'Pause during tool'})
        assert paused.status_code==200
        release.set();result=call.result()
    assert result.status_code==200,result.text
    assert result.json()['run']['status']=='paused' and len(result.json()['toolCalls'])==1
    assert execute(client,source,initial).status_code==409
    resumed=preview(client,source,initial)
    assert resumed['turn']==2
    assert len(client.app.state.runtime.repository.get(initial['runId']).tool_calls)==1


def test_six_serial_tools_allowed_but_seventh_proposal_rejected_before_execution(client):
    class Six(FakeLlmProvider):
        calls=0
        def execute_prepared(self,call):
            self.calls+=1
            binding=call.request_body_input()['manifest'][0]
            proposed=[{'callId':f'call-{self.calls}-{i}','name':'kb.search','arguments':{
                'identity':binding['identity'],'revision':binding['revision'],'locatorIds':binding['locatorIds'],
                'query':'absent'}} for i in range(6 if self.calls==1 else 1)]
            return LlmCallResult(ResearchDecision(action='continue',toolCalls=proposed,evidenceIds=[],missingInformation=[]),ProviderUsage(inputTokens=1,outputTokens=1))
    model=Six();client.app.state.harness_service.research_provider=model
    source,initial=start(client)
    first=execute(client,source,initial);assert first.status_code==200,first.text
    assert len(first.json()['toolCalls'])==6
    second=execute(client,source,preview(client,source,initial))
    assert second.status_code==502 and len(client.app.state.runtime.repository.get(initial['runId']).tool_calls)==6


def test_cumulative_budget_exhaustion_stops_before_next_model_request(client):
    source,initial=start(client)
    runtime=client.app.state.runtime
    runtime.repository.update(initial['runId'],lambda report:setattr(report,'consumed_tokens',29999))
    response=client.post(f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
    assert response.status_code==422 and response.json()['error']['code']=='REQUEST_BUDGET_EXCEEDED'
    saved=runtime.repository.get(initial['runId'])
    assert saved.research.status=='exhausted' and saved.run.status=='error'
    assert not saved.tool_calls and all(call.status=='prepared' for call in saved.requests)


def test_saved_known_research_response_restores_without_automatic_tool_or_model(tmp_path,source_root):
    runtime_path=tmp_path/'restart-runtime.sqlite3'
    def app():return create_app(context_source_root=source_root,rag_index_path=tmp_path/'index.sqlite3',
        plugin_root=tmp_path/'plugins',runtime_path=runtime_path)
    with TestClient(app(),raise_server_exceptions=False) as first_client:
        source,initial=start(first_client)
        runtime=first_client.app.state.runtime;report=runtime.repository.get(initial['runId'])
        call=report.requests[0]
        runtime.claim(report.run.id,call.id,call.prepared_call)
        result=FakeLlmProvider().execute_prepared(call.prepared_call)
        runtime.returned(report.run.id,call.id,result.output,result.usage)
        assert runtime.repository.get(report.run.id).tool_calls==[]
    with TestClient(app(),raise_server_exceptions=False) as restarted:
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert saved.research.turns[0].status=='tools_pending' and saved.tool_calls==[]
        assert execute(restarted,source,initial).status_code==409
        renewed=preview(restarted,source,initial)
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert len(saved.tool_calls)==1 and saved.tool_calls[0].status=='completed'
        assert renewed['turn']==2 and saved.context is None
        assert execute(restarted,source,renewed).status_code==200


def test_interrupted_research_model_claim_is_unknown_after_actual_app_restart(tmp_path,source_root):
    runtime_path=tmp_path/'interrupted-runtime.sqlite3'
    def app():return create_app(context_source_root=source_root,rag_index_path=tmp_path/'index.sqlite3',
        plugin_root=tmp_path/'plugins',runtime_path=runtime_path)
    with TestClient(app(),raise_server_exceptions=False) as value:
        source,initial=start(value)
        report=value.app.state.runtime.repository.get(initial['runId']);call=report.requests[0]
        value.app.state.runtime.claim(report.run.id,call.id,call.prepared_call)
    with TestClient(app(),raise_server_exceptions=False) as restarted:
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert saved.run.status=='outcome_unknown' and saved.research.turns[0].status=='outcome_unknown'
        response=restarted.post(f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
        assert response.status_code==409 and saved.tool_calls==[]


def test_research_input_reopen_creates_linked_research_and_manual_tools_cannot_bypass_turn(client):
    source,initial=start(client)
    saved=client.app.state.runtime.repository.get(initial['runId'])
    args=FakeLlmProvider().execute_prepared(saved.requests[0].prepared_call).output.tool_calls[0]
    direct=client.post(f"/api/runtime/runs/{initial['runId']}/tools/execute",json={'sourceRequest':source,'call':args.model_dump(by_alias=True)})
    assert direct.status_code==409 and not client.app.state.runtime.repository.get(initial['runId']).tool_calls
    changed={**source,'goal':'A revised goal'}
    response=client.post(f"/api/runtime/runs/{initial['runId']}/reopen",json={'sourceRequest':changed})
    assert response.status_code==200,response.text
    reopened=response.json();assert reopened['stage']=='research' and reopened['runId']!=initial['runId']
    linked=client.app.state.runtime.repository.get(reopened['runId'])
    assert linked.run.parent_run_id==initial['runId'] and linked.run.session_id==initial['sessionId']
    assert linked.research is not None and linked.selection.goal=='A revised goal'


def test_pause_arriving_after_resume_validation_blocks_pending_tools(client,monkeypatch):
    from frag_api.services.research_checkpoint import checkpoint_research
    source,initial=start(client)
    runtime=client.app.state.runtime;loop=client.app.state.research
    saved=runtime.repository.get(initial['runId']);call=saved.requests[0]
    runtime.claim(saved.run.id,call.id,call.prepared_call)
    result=FakeLlmProvider().execute_prepared(call.prepared_call)
    runtime.returned(saved.run.id,call.id,result.output,result.usage)
    checkpoint_research(runtime,saved.run.id,call.id,result.output)
    entered,release=threading.Event(),threading.Event();original=loop.validate_source
    def held(report,selected):
        fresh=original(report,selected)
        entered.set();assert release.wait(3)
        return fresh
    monkeypatch.setattr(loop,'validate_source',held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
        assert entered.wait(3)
        paused=client.post(f"/api/runtime/runs/{initial['runId']}/review",json={'decision':'paused',
            'checklist':saved.selection.task.model_dump(by_alias=True),'note':'A newer explicit pause'})
        assert paused.status_code==200
        release.set();response=pending.result()
    assert response.status_code==409
    current=runtime.repository.get(initial['runId'])
    assert current.run.status=='paused' and current.tool_calls==[]
    monkeypatch.setattr(loop,'validate_source',original)
    resumed=preview(client,source,initial)
    assert resumed['turn']==2 and len(runtime.repository.get(initial['runId']).tool_calls)==1


def test_over_budget_known_research_response_is_not_restored_or_executed(tmp_path,source_root):
    runtime_path=tmp_path/'overbudget-runtime.sqlite3'
    def app():return create_app(context_source_root=source_root,rag_index_path=tmp_path/'index.sqlite3',
        plugin_root=tmp_path/'plugins',runtime_path=runtime_path)
    with TestClient(app(),raise_server_exceptions=False) as client:
        source,initial=start(client)
        runtime=client.app.state.runtime;report=runtime.repository.get(initial['runId']);call=report.requests[0]
        runtime.claim(report.run.id,call.id,call.prepared_call)
        result=FakeLlmProvider().execute_prepared(call.prepared_call)
        runtime.returned(report.run.id,call.id,result.output,ProviderUsage(inputTokens=30001,outputTokens=1))
    with TestClient(app(),raise_server_exceptions=False) as restarted:
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert saved.requests[0].error_code=='REQUEST_BUDGET_EXCEEDED'
        assert saved.research.status=='exhausted' and saved.tool_calls==[]
        assert restarted.post(f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source}).status_code==409


def test_known_context_return_that_drops_research_gaps_is_rejected_on_restart(tmp_path,source_root):
    runtime_path=tmp_path/'gaps-runtime.sqlite3'
    def app():return create_app(context_source_root=source_root,rag_index_path=tmp_path/'index.sqlite3',
        plugin_root=tmp_path/'plugins',runtime_path=runtime_path)
    with TestClient(app(),raise_server_exceptions=False) as client:
        client.app.state.harness_service.research_provider=FirstOnly()
        source,initial=start(client,two_sources(client))
        assert execute(client,source,initial).status_code==200
        assert execute(client,source,preview(client,source,initial)).status_code==200
        formal=preview(client,source,initial)
        runtime=client.app.state.runtime;report=runtime.repository.get(initial['runId'])
        call=next(item for item in report.requests if item.id==report.run.active_call_id)
        runtime.claim(report.run.id,call.id,call.prepared_call)
        result=FakeLlmProvider().execute_prepared(call.prepared_call);result.output.missing_information=[]
        runtime.returned(report.run.id,call.id,result.output,result.usage)
    with TestClient(app(),raise_server_exceptions=False) as restarted:
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert saved.context is None and saved.requests[-1].error_code=='INVALID_PERSISTED_OUTPUT'
        assert saved.research.missing_information==['The unobserved second section remains unknown.']


def test_pause_after_resume_tools_returns_cannot_be_absorbed_by_preview(client,monkeypatch):
    source,initial=start(client)
    runtime=client.app.state.runtime;loop=client.app.state.research
    original=loop._resume_tools;entered,release=threading.Event(),threading.Event()
    def held(*args,**kwargs):
        value=original(*args,**kwargs)
        entered.set();assert release.wait(3)
        return value
    monkeypatch.setattr(loop,'_resume_tools',held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
        assert entered.wait(3)
        saved=runtime.repository.get(initial['runId'])
        paused=client.post(f"/api/runtime/runs/{initial['runId']}/review",json={'decision':'paused',
            'checklist':saved.selection.task.model_dump(by_alias=True),'note':'Pause after resume returned'})
        assert paused.status_code==200
        release.set();response=pending.result()
    assert response.status_code==409
    current=runtime.repository.get(initial['runId'])
    assert current.run.status=='paused' and current.tool_calls==[] and len(current.requests)==1


def test_pause_during_resumed_tool_stops_preview_without_repeating_completed_read(client):
    from frag_api.services.research_checkpoint import checkpoint_research
    source,initial=start(client)
    runtime=client.app.state.runtime;loop=client.app.state.research
    report=runtime.repository.get(initial['runId']);call=report.requests[0]
    runtime.claim(report.run.id,call.id,call.prepared_call)
    result=FakeLlmProvider().execute_prepared(call.prepared_call)
    runtime.returned(report.run.id,call.id,result.output,result.usage)
    checkpoint_research(runtime,report.run.id,call.id,result.output)
    original=client.app.state.kb_tools.registry.get('kb.read')
    entered,release=threading.Event(),threading.Event();executions=[]
    def held(payload):
        executions.append(payload['callId']);entered.set();assert release.wait(3)
        return original.execute(payload)
    client.app.state.kb_tools.registry._bindings['kb.read']=replace(original,execute=held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f"/api/runtime/runs/{initial['runId']}/research/preview",json={'sourceRequest':source})
        assert entered.wait(3)
        paused=client.post(f"/api/runtime/runs/{initial['runId']}/review",json={'decision':'paused',
            'checklist':report.selection.task.model_dump(by_alias=True),'note':'Pause during resumed tool'})
        assert paused.status_code==200
        release.set();response=pending.result()
    assert response.status_code==409
    saved=runtime.repository.get(initial['runId'])
    assert saved.run.status=='paused' and len(saved.requests)==1 and len(saved.tool_calls)==1
    assert saved.tool_calls[0].status=='completed' and executions==['fake-read-1']
    renewed=preview(client,source,initial)
    assert renewed['turn']==2 and executions==['fake-read-1']


def test_known_inference_return_that_drops_gaps_is_rejected_on_restart(tmp_path,source_root):
    runtime_path=tmp_path/'inference-gaps-runtime.sqlite3'
    def app():return create_app(context_source_root=source_root,rag_index_path=tmp_path/'index.sqlite3',
        plugin_root=tmp_path/'plugins',runtime_path=runtime_path)
    with TestClient(app(),raise_server_exceptions=False) as client:
        client.app.state.harness_service.research_provider=FirstOnly()
        source,initial=start(client,two_sources(client))
        assert execute(client,source,initial).status_code==200
        assert execute(client,source,preview(client,source,initial)).status_code==200
        assert execute(client,source,preview(client,source,initial)).status_code==200
        formal=preview(client,source,initial)
        assert formal['stage']=='inference'
        runtime=client.app.state.runtime;report=runtime.repository.get(initial['runId'])
        call=next(item for item in report.requests if item.id==report.run.active_call_id)
        runtime.claim(report.run.id,call.id,call.prepared_call)
        result=FakeLlmProvider().execute_prepared(call.prepared_call);result.output.missing_information=[]
        runtime.returned(report.run.id,call.id,result.output,result.usage)
    with TestClient(app(),raise_server_exceptions=False) as restarted:
        saved=restarted.app.state.runtime.repository.get(initial['runId'])
        assert saved.model_output is None and saved.context is not None
        assert saved.requests[-1].error_code=='INVALID_PERSISTED_OUTPUT'
        assert saved.context.missing_information==['The unobserved second section remains unknown.']
