from pathlib import Path
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from frag_api.main import create_app
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.schemas.native import SearchInput, ReadInput, CompleteInput, SourceProfile
from frag_api.schemas.memory import MemoryCandidateRequest, MemoryPromotionRequest, MemoryRevisionRequest, MemoryConflictRequest, MemoryConflictResolutionRequest, MemoryVersionRequest
from frag_api.errors import PolicyRejectedError, RuntimeConflictError, RagIndexStaleError


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'kb'
    root.mkdir()
    (root / 'a.md').write_text('# Alpha\nEvidence alpha apples.\napi_key=synthetic-secret\n', encoding='utf8')
    (root / 'b.md').write_text('# Beta\nEvidence beta apples.\n', encoding='utf8')
    (root / 'excluded').mkdir()
    (root / 'excluded/private.md').write_text('apples forbidden subtree')
    (root / 'AGENTS.md').write_text('apples forbidden instructions')
    app = create_app(tmp_path / 'state', 'x' * 64)
    tools = app.state.tools
    profile = tools.repository.save_profile(SourceProfile(id='kb', root=str(root), approved=True, excludedPaths=['excluded']))
    try:
        yield root, tools, profile, app
    finally:
        tools.repository.close()


def search(tools, query='apples'):
    pack = tools.search(SearchInput(query=query, topK=10))
    return tools.complete(CompleteInput(runId=pack['runId']))


def test_multifile_search_read_and_source_change(setup):
    root, tools, profile, _ = setup
    assert tools.index('kb').build()['documentCount'] == 2
    pack = search(tools)
    assert {e['relativePath'] for e in pack['evidence']} == {'a.md','b.md'}
    assert 'synthetic-secret' not in canonical_json(pack)
    assert tools.repository.get(pack['runId']).result_digest == fingerprint(pack)
    read = tools.read(ReadInput(searchRunId=pack['runId'], evidenceIds=[pack['evidence'][0]['evidenceId']]))
    tools.complete(CompleteInput(runId=read['runId']))
    with pytest.raises(RuntimeConflictError):
        tools.complete(CompleteInput(runId=read['runId']))
    with pytest.raises(PolicyRejectedError):
        tools.read(ReadInput(searchRunId=pack['runId'], evidenceIds=['outside']))
    pending = tools.search(SearchInput(query='apples'))
    (root/'b.md').write_text('# Changed\napples changed')
    with pytest.raises(RagIndexStaleError):
        tools.complete(CompleteInput(runId=pending['runId']))
    tools.index('kb').build()
    (root/'b.md').unlink()
    with pytest.raises(RagIndexStaleError):
        tools.index('kb').ready()
    assert tools.index('kb').build()['documentCount'] == 1
    assert len(search(tools)['evidence']) == 1


def test_memory_manual_review_pins_and_legacy_are_readonly(setup):
    _, tools, profile, _ = setup
    tools.index('kb').build()
    pack = search(tools)
    candidate = tools.memory.candidate(MemoryCandidateRequest(runId=pack['runId'], text='Reviewed apple background'))
    active = tools.memory.promote(candidate.id, MemoryPromotionRequest(version=1, reviewed=True, note='Checked provenance and scope'))
    assert tools.memory.recommend('apple', tools.memory.sources(tools.repository.get(pack['runId'])))[0].id == active.id
    profile = tools.repository.save_profile(profile.model_copy(update={'selected_memory':[
        __import__('frag_api.schemas.memory', fromlist=['MemorySelection']).MemorySelection(memoryId=active.id, version=active.version)]}))
    pending = tools.search(SearchInput(query='apples'))
    assert pending['memoryBackground'][0]['version'] == active.version
    tools.memory.revise(active.id, MemoryRevisionRequest(version=active.version, text='Edited background'))
    with pytest.raises(PolicyRejectedError):
        tools.complete(CompleteInput(runId=pending['runId']))
    with tools.repository.connection() as db:
        db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        body = json.dumps({'unknownLegacySchema':True,'preparedCall':{'doNotReplay':True}})
        db.execute('INSERT INTO runs VALUES (?,?)', ('old', body))
        legacy = active.model_copy(update={'id':'legacy','provenance_run_id':'old'})
        tools.memory._insert(db, legacy)
    assert tools.memory.records()[-1].id == active.id
    with pytest.raises(PolicyRejectedError):
        tools.memory.revise('legacy', MemoryRevisionRequest(version=legacy.version, text='Not permitted'))
    with sqlite3.connect(tools.repository.path) as db:
        assert db.execute('SELECT record FROM runs WHERE id="old"').fetchone()[0] == body


def test_private_api_strict_input_no_old_routes(setup):
    _, tools, _, app = setup
    client = TestClient(app)
    auth = {'authorization':'Bearer '+'x'*64}
    assert client.get('/api/health').status_code == 403
    assert client.get('/api/health', headers={**auth,'origin':'https://untrusted.example'}).status_code == 403
    assert client.get('/api/health', headers=auth).json()['serviceVersion'] == '1.13.3'
    for body in ['{"query":"apples","query":"other"}', '{"query":"apples","topK":NaN}', '{"query":"apples","path":"../secret"}']:
        assert client.post('/api/tools/frag_search', headers=auth, content=body).status_code == 422
    assert client.post('/api/manage/source-save', headers=auth, json={'id':'bad','root':'invalid','approved':1}).status_code == 422
    assert client.post('/api/tools/frag_search', headers=auth, content='x'*65537).status_code == 413
    for path in ['/api/agents/ahp','/api/research/preview','/api/harness/inference','/api/plugins']:
        assert client.get(path, headers=auth).status_code == 404
    tools.index('kb').build()
    pack = client.post('/api/tools/frag_search', headers=auth, json={'query':'apples'}).json()
    final = client.post('/api/tools/complete', headers=auth, json={'runId':pack['runId'],'omittedEvidenceIds':[pack['evidence'][-1]['evidenceId']],'tokenCount':17}).json()
    assert len(final['evidence']) == len(pack['evidence'])-1
    assert tools.repository.get(pack['runId']).output_tokens == 17


def test_index_transaction_rollback_owner_lease_and_path_scope(setup):
    root, tools, profile, _ = setup
    index = tools.index('kb')
    index.build()
    revision = index.repository.snapshot().index_revision
    from frag_api.repositories.rag_index_repository import IndexDocument
    with pytest.raises(Exception):
        index.repository.rebuild([IndexDocument('duplicate','kb','kb','hash')]*2, [], [], 'bad', {})
    assert index.repository.snapshot().index_revision == revision
    from frag_api.repositories.tool_store import ToolStore
    with pytest.raises(OSError):
        ToolStore(tools.repository.path)
    from frag_api.services.source_index import SourceIndex
    with pytest.raises(PolicyRejectedError):
        SourceIndex(profile.model_copy(update={'excluded_paths':['../outside']}), tools.index_root)
    with pytest.raises(PolicyRejectedError):
        SourceIndex(profile.model_copy(update={'root':'relative'}), tools.index_root)


def test_profile_revision_cancellation_and_scope_changes(setup):
    _, tools, profile, _ = setup
    tools.index('kb').build()
    pending = tools.search(SearchInput(query='apples'))
    tools.complete(CompleteInput(runId=pending['runId'],cancelled=True))
    assert tools.repository.get(pending['runId']).status == 'cancelled'
    pending = tools.search(SearchInput(query='apples'))
    tools.repository.save_profile(profile.model_copy(update={'enabled':False}))
    with pytest.raises(PolicyRejectedError):
        tools.complete(CompleteInput(runId=pending['runId']))


def test_redaction_handles_legacy_secret_fields_and_quoted_source_keys():
    from frag_api.services.runtime_policy import redact, redact_value
    assert 'synthetic-private-value' not in redact('{"api_key":"synthetic-private-value"}')
    assert redact_value({'nested':{'authorization':'synthetic-private-value'}})['nested']['authorization']=='[REDACTED_SECRET]'


def test_restart_only_marks_new_prepared_deliveries_never_legacy(setup):
    _,tools,_,_=setup
    tools.index('kb').build()
    pending=tools.search(SearchInput(query='apples'))
    with tools.repository.connection() as db:
        db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        db.execute('INSERT INTO runs VALUES (?,?)',('legacy','{"status":"in_flight","unknown":true}'))
    path=tools.repository.path
    tools.repository.close()
    from frag_api.repositories.tool_store import ToolStore
    reopened=ToolStore(path)
    try:
        assert reopened.get(pending['runId']).status=='interrupted'
        with reopened.connection() as db:
            assert json.loads(db.execute('SELECT record FROM runs WHERE id=?',('legacy',)).fetchone()[0])['status']=='in_flight'
    finally:
        reopened.close()


def test_memory_content_versions_review_revisions_and_unchanged_save(setup):
    _, tools, _, _ = setup
    tools.index('kb').build()
    pack = search(tools)
    candidate = tools.memory.candidate(MemoryCandidateRequest(runId=pack['runId'], text='First background'))
    active = tools.memory.promote(candidate.id, MemoryPromotionRequest(version=candidate.version, reviewed=True, note='Reviewed'))
    assert (candidate.content_version, candidate.version) == (1, 1)
    assert (active.content_version, active.version) == (1, 2)
    unchanged = tools.memory.revise(active.id, MemoryRevisionRequest(version=active.version, text='  First background  '))
    assert unchanged == active and len(tools.memory.versions(active.id)) == 2
    edited = tools.memory.revise(active.id, MemoryRevisionRequest(version=active.version, text='Second background'))
    assert (edited.content_version, edited.version, edited.status) == (2, 3, 'candidate')
    with pytest.raises(RuntimeConflictError):
        tools.memory.promote(edited.id, MemoryPromotionRequest(version=active.version, reviewed=True, note='Stale review'))
    promoted = tools.memory.promote(edited.id, MemoryPromotionRequest(version=edited.version, reviewed=True, note='Reviewed edit'))
    assert (promoted.content_version, promoted.version) == (2, 4)
    rescoped = tools.memory.revise(promoted.id, MemoryRevisionRequest(version=promoted.version, text=promoted.text, general=True))
    assert (rescoped.content_version, rescoped.version) == (3, 5)
    retired = tools.memory.retire(rescoped.id, MemoryVersionRequest(version=rescoped.version))
    assert (retired.content_version, retired.version) == (3, 6)


def test_historical_memory_content_versions_are_derived_without_row_rewrites(setup):
    _, tools, _, _ = setup
    tools.index('kb').build()
    pack = search(tools)
    candidate = tools.memory.candidate(MemoryCandidateRequest(runId=pack['runId'], text='Original'))
    active = tools.memory.promote(candidate.id, MemoryPromotionRequest(version=1, reviewed=True, note='Reviewed'))
    tools.memory.revise(active.id, MemoryRevisionRequest(version=active.version, text='Changed'))
    with tools.repository.connection() as db:
        rows = db.execute('SELECT version,record FROM memory_versions WHERE id=? ORDER BY version',(active.id,)).fetchall()
        for revision, body in rows:
            value = json.loads(body)
            value.pop('contentVersion', None)
            db.execute('UPDATE memory_versions SET record=? WHERE id=? AND version=?',(json.dumps(value),active.id,revision))
        before = db.execute('SELECT record FROM memory_versions WHERE id=? ORDER BY version',(active.id,)).fetchall()
    assert [record.content_version for record in tools.memory.versions(active.id)] == [1,1,2]
    assert tools.memory.records()[0].content_version == 2
    with tools.repository.connection() as db:
        assert before == db.execute('SELECT record FROM memory_versions WHERE id=? ORDER BY version',(active.id,)).fetchall()


def test_memory_conflict_changes_keep_content_version_and_reject_stale_review(setup):
    _, tools, _, _ = setup
    tools.index('kb').build()
    pack = search(tools)
    records = [tools.memory.candidate(MemoryCandidateRequest(runId=pack['runId'], text=text)) for text in ('First','Second')]
    conflict = tools.memory.conflict(MemoryConflictRequest(memoryIds=[r.id for r in records]))
    assert [(r.content_version,r.version) for r in conflict] == [(1,2),(1,2)]
    with pytest.raises(RuntimeConflictError):
        tools.memory.conflict(MemoryConflictResolutionRequest(memoryIds=[r.id for r in records],versions=[{'memoryId':r.id,'version':1} for r in records],reviewed=True,note='Outdated'),resolve=True)
    resolved = tools.memory.conflict(MemoryConflictResolutionRequest(memoryIds=[r.id for r in records],versions=[{'memoryId':r.id,'version':r.version} for r in conflict],reviewed=True,note='Reviewed both'),resolve=True)
    assert [(r.content_version,r.version) for r in resolved] == [(1,3),(1,3)]


def test_exact_run_lookup_beyond_overview_limit_and_no_legacy_export(setup):
    _, tools, _, app = setup
    tools.index('kb').build()
    pack = search(tools)
    original = tools.repository.get(pack['runId'])
    for i in range(201):
        key = f'newer-{i}'
        tools.repository.save(original.model_copy(update={'id':key,'pack':{**original.pack,'runId':key}}))
    with tools.repository.connection() as db:
        db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        db.execute('INSERT INTO runs VALUES (?,?)',('old','{"privateArchive":true}'))
    client = TestClient(app)
    auth = {'authorization':'Bearer '+'x'*64}
    overview = client.post('/api/manage/overview',headers=auth,json={}).json()
    assert len(overview['runs']) == 200 and original.id not in {r['id'] for r in overview['runs']}
    assert 'legacyRuns' not in overview and 'privateArchive' not in canonical_json(overview)
    reply = client.post('/api/manage/run-get',headers=auth,json={'runId':original.id})
    assert reply.status_code == 200 and reply.json()['id'] == original.id
    assert client.post('/api/manage/run-get',headers=auth,json={'runId':'old'}).status_code == 404
    assert client.post('/api/manage/run-get',headers=auth,json={'runId':'missing'}).status_code == 404
    for body in ({'runId':''},{'runId':'a'*65},{'runId':original.id,'path':'unapproved'}):
        assert client.post('/api/manage/run-get',headers=auth,json=body).status_code == 422
    assert client.post('/api/manage/run-get',json={'runId':original.id}).status_code == 403
    with tools.repository.connection() as db:
        assert db.execute('SELECT record FROM runs WHERE id=?',('old',)).fetchone()[0] == '{"privateArchive":true}'
