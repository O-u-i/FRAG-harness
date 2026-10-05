"""Reviewed memory lifecycle, provenance and scope checks with synthetic records."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from frag_api.errors import PolicyRejectedError, RuntimeConflictError, RuntimeNotFoundError
from frag_api.repositories.runtime_repository import RuntimeRepository
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.schemas.governance import PreparedCall, SourceBinding, SourceIdentity, TaskContract
from frag_api.schemas.memory import (
    MemoryCandidateRequest, MemoryConflictRequest, MemoryConflictResolutionRequest,
    MemoryPromotionRequest, MemoryRevisionRequest, MemorySelection, MemoryVersionRequest,
)
from frag_api.schemas.rag import RagGroundedAnswer
from frag_api.schemas.runtime import AttemptRecord, RevisionRecord, RunRecord, RunReport, SelectionSnapshot
from frag_api.services.memory_service import MemoryService
from frag_api.services.runtime_service import RuntimeService


def source(resource="source-a", *, workspace=None, namespace="synthetic-suite"):
    return SourceBinding(identity=SourceIdentity(kind="fc_record" if workspace else "local_file",
        namespace=namespace, resourceId=resource, workspaceId=workspace),
        revision="source-revision-1", parserVersion="synthetic-parser-1", locatorIds=("section-1",), evidenceIds=("evidence-1",))


def answer(text):
    return RagGroundedAnswer(answer=text, claims=[{"text":text, "evidenceIds":["evidence-1"]}],
        missingInformation=[], disclaimer="Synthetic test result.")


@pytest.fixture
def memory(tmp_path):
    return MemoryService(RuntimeService(RuntimeRepository(tmp_path / "memory-runtime.sqlite3")))


def saved_run(memory, sources=None, text="Review conditions before using an answer.", *, revision=False, output=True):
    sources = sources or (source(),)
    runtime = memory.runtime
    session = runtime.create_session("Synthetic memory origin")
    result = answer(text)
    payload = result.model_dump(by_alias=True)
    run_id = session.id + "run"
    prepared = PreparedCall(purpose="inference", provider="fake", model="synthetic-inference",
        endpoint="local://synthetic", transport="fake", body='{"max_output_tokens":2000}',
        binding=canonical_json({"sources":[item.model_dump(by_alias=True) for item in sources]}),
        timeoutSeconds=120, estimatedInputTokens=10, fingerprint="f" * 64)
    report = RunReport(session=session,
        run=RunRecord(id=run_id, sessionId=session.id, parentRunId=None, kind="harness", status="awaiting_review",
            createdAt=session.created_at, updatedAt=session.created_at, version=1, activeCallId=None),
        selection=SelectionSnapshot(goal="Synthetic memory test", sourceBindings=sources, candidateEvidence=[],
            task=TaskContract(), input={}),
        requests=[AttemptRecord(id="attempt-1", stage="inference", status="completed", preparedCall=prepared,
            createdAt=session.created_at, output=payload, outputDigest=fingerprint(payload), structuralValidation="PASS")],
        context=None, modelOutput=result if output else None, reviews=[], revisions=[],
        consumedTokens=10, runTokenLimit=30_000, structuralValidation="PASS", semanticReview="NOT_RUN", limitations=[])
    if revision:
        revised = answer("Human revision background.")
        report.revisions.append(RevisionRecord(id="revision-1", createdAt=session.created_at, result=revised,
            contentDigest=fingerprint(revised.model_dump(by_alias=True))))
    runtime.repository.create(report)
    return report


def candidate(memory, *, sources=None, text="Review conditions before using an answer.", general=False):
    report = saved_run(memory, sources=sources, text=text)
    return memory.candidate(MemoryCandidateRequest(runId=report.run.id, general=general))


def promote(memory, item):
    return memory.promote(item.id, MemoryPromotionRequest(version=item.version, reviewed=True, note="Reviewed synthetic provenance and scope."))


def choice(item):
    return MemorySelection(memoryId=item.id, version=item.version)


def test_candidate_requires_review_edit_and_promotion_then_persists_history(memory):
    initial = candidate(memory)
    assert initial.status == "candidate" and not initial.general
    assert memory.recommend("conditions", (source(),)) == []
    with pytest.raises(PolicyRejectedError):
        memory.select([choice(initial)], (source(),))
    edited = memory.revise(initial.id, MemoryRevisionRequest(version=1, text="Review conditions and missing information."))
    active = promote(memory, edited)
    assert (active.version, active.status) == (3, "active")
    assert memory.select([choice(active)], (source(),))[0]["text"] == edited.text
    reopened = MemoryService(RuntimeService(RuntimeRepository(memory.repository.path)))
    assert [item.status for item in reopened.versions(initial.id)] == ["candidate", "candidate", "active"]
    assert reopened.records() == [active]
    retired = reopened.retire(active.id, MemoryVersionRequest(version=active.version))
    assert retired.status == "retired" and retired.version == 4
    assert reopened.recommend("conditions", (source(),)) == []
    with pytest.raises(PolicyRejectedError):
        reopened.select([choice(active)], (source(),))


def test_full_identity_subset_and_workspace_isolation(memory):
    sources = (source("record", workspace="workspace-a"), source("other", workspace="workspace-a"))
    item = promote(memory, candidate(memory, sources=sources, text="Financial background review."))
    assert memory.select([choice(item)], sources)
    for selected in ((sources[0],), (source("record", workspace="workspace-b"), sources[1]),
                     (source("record", workspace="workspace-a", namespace="other-provider"), sources[1])):
        assert memory.recommend("Financial", selected) == []
        with pytest.raises(PolicyRejectedError):
            memory.select([choice(item)], selected)
    generic = promote(memory, candidate(memory, sources=sources, text="General review process.", general=True))
    assert memory.recommend("General", (source("unrelated"),)) == [generic]


def test_conflict_blocks_both_records_and_resolution_requires_current_review(memory):
    first, second = [promote(memory, candidate(memory, text=text)) for text in ("Verify allowed conditions.", "Verify contrary conditions.")]
    conflicted = memory.conflict(MemoryConflictRequest(memoryIds=[first.id, second.id]))
    assert all(item.conflicts for item in conflicted)
    assert memory.recommend("conditions", (source(),)) == []
    with pytest.raises(PolicyRejectedError):
        memory.select([choice(conflicted[0])], (source(),))
    resolution = MemoryConflictResolutionRequest(memoryIds=[first.id, second.id], versions=[choice(item) for item in conflicted],
        reviewed=True, note="The two background records concern distinct conditions.")
    resolved = memory.conflict(resolution, resolve=True)
    assert all(not item.conflicts and item.status == "active" for item in resolved)
    assert len(memory.recommend("conditions", (source(),))) == 2
    with pytest.raises(RuntimeConflictError):
        memory.conflict(resolution, resolve=True)


def test_conflict_resolution_after_concurrent_edit_rejects_stale_review(memory):
    first, second = [promote(memory, candidate(memory)) for _ in range(2)]
    conflicted = memory.conflict(MemoryConflictRequest(memoryIds=[first.id, second.id]))
    request = MemoryConflictResolutionRequest(memoryIds=[first.id, second.id], versions=[choice(item) for item in conflicted],
        reviewed=True, note="Reviewed these exact versions.")
    memory.revise(conflicted[0].id, MemoryRevisionRequest(version=conflicted[0].version, text="Different background conditions."))
    with pytest.raises(RuntimeConflictError):
        memory.conflict(request, resolve=True)
    assert all(item.conflicts for item in memory.records())


def test_native_fts_english_chinese_zero_match_scope_filter_before_limit(memory):
    for index in range(4):
        promote(memory, candidate(memory, text=f"Review evidence risk limits synthetic {index}."))
    for index in range(4):
        promote(memory, candidate(memory, sources=(source("excluded"),), text=f"Risk risk risk synthetic excluded {index}."))
    recommendations = memory.recommend("risk", (source(),))
    assert len(recommendations) == 3
    assert all(item.scope == [source().identity] for item in recommendations)
    chinese = promote(memory, candidate(memory, text="当前证据仍然不足，必须保留风险约束与未知条件。"))
    assert memory.recommend("风险约束", (source(),)) == [chinese]
    assert memory.recommend("橙色火星", (source(),)) == []
    assert memory.recommend('" OR * --', (source(),)) == []


def test_stale_version_concurrent_mutations_have_one_winner(memory):
    initial = candidate(memory)
    def edit(text):
        try:
            return memory.revise(initial.id, MemoryRevisionRequest(version=initial.version, text=text)).version
        except RuntimeConflictError:
            return "stale"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(edit, ["First edited conditions.", "Second edited conditions."]))
    assert sorted(outcomes, key=str) == [2, "stale"]
    assert len(memory.versions(initial.id)) == 2


def test_secret_redaction_default_origin_revision_and_unknown_run(memory):
    memory.runtime.secret_values = ("synthetic-secret-value",)
    report = saved_run(memory, text="synthetic-secret-value user@example.invalid api_key=example-secret", revision=True)
    initial = memory.candidate(MemoryCandidateRequest(runId=report.run.id))
    assert "synthetic-secret-value" not in initial.text and "user@example.invalid" not in initial.text and "example-secret" not in initial.text
    revised = memory.candidate(MemoryCandidateRequest(runId=report.run.id, revisionId="revision-1"))
    assert revised.text == "Human revision background." and revised.provenance_revision_id == "revision-1"
    active = memory.promote(initial.id, MemoryPromotionRequest(version=initial.version, reviewed=True,
        note="Reviewed synthetic-secret-value user@example.invalid api_key=example-secret"))
    assert active.review_note.startswith("Reviewed ")
    assert all(secret not in active.review_note for secret in ("synthetic-secret-value", "user@example.invalid", "example-secret"))
    memory.revise(active.id, MemoryRevisionRequest(version=active.version,
        text="Edited synthetic-secret-value user@example.invalid api_key=example-secret"))
    with pytest.raises(RuntimeNotFoundError):
        memory.candidate(MemoryCandidateRequest(runId="unknown-run"))
    empty = saved_run(memory, output=False)
    with pytest.raises(RuntimeConflictError):
        memory.candidate(MemoryCandidateRequest(runId=empty.run.id, text="Unrelated explicit background."))
    empty_revision = saved_run(memory, output=False, revision=True)
    with pytest.raises(RuntimeConflictError):
        memory.candidate(MemoryCandidateRequest(runId=empty_revision.run.id, revisionId="revision-1"))
    with memory.repository.connection() as db:
        records = db.execute("SELECT record FROM memory_versions").fetchall()
        tokens = db.execute("SELECT tokens FROM memory_fts").fetchall()
    assert all("synthetic-secret-value" not in row[0] and "user@example.invalid" not in row[0] for row in records)
    assert all(not ({"synthetic", "value", "user", "example", "invalid"} & set(row[0].split())) for row in tokens)


@pytest.mark.parametrize("target", ["model", "revision"])
def test_candidate_provenance_rejects_tampered_committed_result(memory, target):
    report = saved_run(memory, revision=True)
    def corrupt(saved):
        if target == "model":
            saved.model_output.answer = "Tampered original."
        else:
            saved.revisions[0].result.answer = "Tampered revision."
    memory.repository.update(report.run.id, corrupt)
    with pytest.raises(RuntimeConflictError):
        memory.candidate(MemoryCandidateRequest(runId=report.run.id, revisionId="revision-1" if target == "revision" else None))


def test_prepared_memory_binding_invalidation_and_existing_transaction(memory, monkeypatch):
    active = promote(memory, candidate(memory))
    sources = (source(),)
    binding = {"sources":[item.model_dump(by_alias=True) for item in sources], "memoryVersions":[choice(active).model_dump(by_alias=True)]}
    with memory.repository.connection() as db:
        def forbidden_connection():
            raise AssertionError("Must reuse the durable claim transaction.")
        with monkeypatch.context() as scoped:
            scoped.setattr(memory.repository, "connection", forbidden_connection)
            memory.validate_bindings(binding, db=db)
    memory.revise(active.id, MemoryRevisionRequest(version=active.version, text="Changed reviewed background."))
    with pytest.raises(PolicyRejectedError):
        memory.validate_bindings(binding)
    with pytest.raises(PolicyRejectedError):
        memory.validate_bindings({**binding, "memoryVersions":[choice(active).model_dump(by_alias=True)] * 2})


def test_memory_schema_version_gate_and_empty_selection(memory):
    memory.validate_bindings({"sources":[source().model_dump(by_alias=True)], "memoryVersions":[]})
    with memory.repository.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        db.execute("UPDATE memory_meta SET schema_version=2")
    with pytest.raises(ValueError, match="Unsupported memory"):
        MemoryService(memory.runtime)


def test_candidate_scope_rejects_altered_saved_source_snapshot(memory):
    report = saved_run(memory)
    def bind_snapshot(saved):
        saved.snapshot_digest = fingerprint(saved.selection.model_dump(by_alias=True))
    memory.repository.update(report.run.id, bind_snapshot)
    def alter_scope(saved):
        saved.selection.source_bindings = (source("different-source"),)
    memory.repository.update(report.run.id, alter_scope)
    with pytest.raises(RuntimeConflictError):
        memory.candidate(MemoryCandidateRequest(runId=report.run.id))


@pytest.mark.parametrize("payload", [{"reviewed":1, "note":"review"}, {"reviewed":True, "note":"  "}])
def test_promotion_requires_explicit_boolean_review_and_note(payload):
    with pytest.raises(ValidationError):
        MemoryPromotionRequest(version=1, **payload)
