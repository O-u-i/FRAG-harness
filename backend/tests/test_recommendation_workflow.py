"""Development cases: synthetic private drafts, never native/provider requests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frag_api.fc_reader import install_fc
from frag_api.main import create_app
from frag_api.repositories.workflow_store import WorkflowStore
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.schemas.native import CompleteInput, FcInput, ReadInput, SearchInput, SourceProfile
from frag_api.schemas.memory import MemoryCandidateRequest
from frag_api.schemas.workflow import CheckResult, EvidenceReference, SyntheticContext, WorkflowReceipt
from frag_api.services.recommendation_workflow import PrivateCandidate, SyntheticRecommendationWorkflow
from frag_api.services.workflow_budget import BudgetRejected, SyntheticTariff, WorkflowBudget


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


PASSED = CheckResult(**dict.fromkeys(("evidence", "numbers", "constraints", "reasoning", "suitability"), "passed"))


@pytest.fixture
def workflow_fixture(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    source = root / "synthetic.md"
    source.write_text("# Foundation\nSynthetic complete bounded evidence for apples.\n", encoding="utf8")
    app = create_app(tmp_path / "state", "x" * 64)
    tools = app.state.tools
    tools.repository.save_profile(SourceProfile(id="kb", root=str(root), approved=True))
    tools.index("kb").build()
    pack = tools.search(SearchInput(query="apples"))
    tools.complete(CompleteInput(runId=pack["runId"]))
    run = tools.repository.get(pack["runId"])
    context = SyntheticContext(evidence=(EvidenceReference(runId=run.id, resultDigest=run.result_digest,
        requiredEvidenceIds=tuple(item["evidenceId"] for item in run.pack["evidence"])),),
        planRevision=fingerprint("synthetic confirmed plan"), constraintsRevision=fingerprint("synthetic constraints"),
        financialFoundationComplete=True)
    sentinel = ("unchecked-private-" + uuid4().hex).encode()
    try:
        yield app, context, PrivateCandidate(sentinel), source
    finally:
        tools.repository.close()


def controller(fixture, **options):
    app, *_ = fixture
    return SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, **options)


def release(gate, fixture, **options):
    _, context, candidate, _ = fixture
    return gate.check_and_release(candidate, context, checker=options.pop("checker", lambda *_: PASSED),
        current_context=options.pop("current_context", lambda: context), **options)


def assert_isolated(fixture, outcome, caplog=None):
    app, _, candidate, _ = fixture
    sentinel = candidate.body.decode()
    assert sentinel not in repr(candidate) + repr(outcome)
    assert sentinel not in canonical_json([item.model_dump(by_alias=True) for item in app.state.workflows.receipts()])
    assert sentinel not in canonical_json([item.model_dump(by_alias=True) for item in app.state.tools.repository.runs()])
    assert sentinel not in canonical_json([item.model_dump(by_alias=True) for item in app.state.tools.memory.records()])
    assert candidate.body not in app.state.tools.repository.path.read_bytes()
    client = TestClient(app, raise_server_exceptions=False)
    for route, body in (("overview", {}), ("run-get", {"runId": outcome.receipt.id if outcome.receipt else uuid4().hex})):
        response = client.post("/api/manage/" + route, headers={"authorization": "Bearer " + "x" * 64}, json=body)
        assert sentinel not in response.text
    if caplog:
        assert sentinel not in caplog.text


def test_exact_checked_synthetic_bytes_only_after_receipt_commit(workflow_fixture, caplog):
    gate = controller(workflow_fixture)
    app, _, candidate, _ = workflow_fixture
    observations = []
    def check(body, _):
        observations.append(app.state.workflows.receipts()[0].stage)
        assert body == candidate.body
        return PASSED
    outcome = release(gate, workflow_fixture, checker=check)
    assert observations == ["checking"]
    assert outcome.checked_bytes == candidate.body
    assert outcome.receipt.status == "checked" and outcome.receipt.reason_code == "CHECKS_PASSED"
    assert app.state.workflows.get(outcome.receipt.id) == outcome.receipt
    assert release(gate, workflow_fixture).checked_bytes is None
    with pytest.raises(Exception):
        app.state.tools.memory.candidate(MemoryCandidateRequest(runId=outcome.receipt.id, text="Not evidence"))
    assert_isolated(workflow_fixture, outcome, caplog)


@pytest.mark.parametrize("changes,reason", [
    ({"evidence": ()}, "EVIDENCE_MISSING"),
    ({"plan_revision": None}, "PLAN_MISSING"),
    ({"constraints_revision": None}, "CONSTRAINTS_MISSING"),
    ({"financial_foundation_complete": False}, "FINANCIAL_FOUNDATION_MISSING"),
])
def test_missing_foundations_never_invoke_checker(workflow_fixture, changes, reason):
    app, context, candidate, _ = workflow_fixture
    gate = controller(workflow_fixture)
    changed = context.model_copy(update=changes)
    def forbidden(*_):
        pytest.fail("Missing foundation reached the checker.")
    result = gate.check_and_release(candidate, changed, checker=forbidden, current_context=lambda: changed)
    assert result.checked_bytes is None and result.reason == reason
    assert_isolated(workflow_fixture, result)


@pytest.mark.parametrize("name,verdict,reason", [
    ("evidence", "failed", "EVIDENCE_MISSING"), ("numbers", "failed", "NUMBERS_CHECK_FAILED"),
    ("constraints", "failed", "CONSTRAINTS_CHECK_FAILED"), ("reasoning", "failed", "REASONING_CHECK_FAILED"),
    ("suitability", "failed", "SUITABILITY_CHECK_FAILED"), ("numbers", "unknown", "CHECK_UNKNOWN"),
    ("suitability", "unknown", "CHECK_UNKNOWN"),
])
def test_check_failure_and_unknown_are_closed(workflow_fixture, name, verdict, reason):
    checks = PASSED.model_copy(update={name: verdict})
    result = release(controller(workflow_fixture), workflow_fixture, checker=lambda *_: checks)
    assert result.reason == reason and result.checked_bytes is None
    assert_isolated(workflow_fixture, result)


def test_private_checker_exception_and_malformed_result_do_not_leak(workflow_fixture, caplog):
    def crash(body, _):
        raise RuntimeError(body.decode())
    result = release(controller(workflow_fixture), workflow_fixture, checker=crash)
    assert result.reason == "CHECK_EXCEPTION" and result.checked_bytes is None
    assert_isolated(workflow_fixture, result, caplog)


@pytest.mark.parametrize("change", ["body", "plan", "constraint", "source", "profile"])
def test_changes_during_checks_require_new_checking(workflow_fixture, change):
    app, context, candidate, source = workflow_fixture
    gate = controller(workflow_fixture)
    latest = context
    def check(*_):
        nonlocal latest
        if change == "body":
            candidate.body = b"rewritten unreviewed candidate"
        elif change in {"plan", "constraint"}:
            latest = context.model_copy(update={"plan_revision" if change == "plan" else "constraints_revision": fingerprint("changed")})
        elif change == "source":
            source.write_text("# Changed\napples revised", encoding="utf8")
        else:
            profile = app.state.tools.repository.profile("kb")
            app.state.tools.repository.save_profile(profile.model_copy(update={"enabled": False}))
        return PASSED
    result = release(gate, workflow_fixture, checker=check, current_context=lambda: latest)
    assert result.checked_bytes is None
    assert result.reason in {"RESULT_CHANGED", "CONTEXT_CHANGED", "EVIDENCE_STALE"}
    assert_isolated(workflow_fixture, result)


def test_required_items_missing_or_windowed_refuse(workflow_fixture):
    app, context, candidate, _ = workflow_fixture
    ref = context.evidence[0].model_copy(update={"required_evidence_ids": ("f" * 24,)})
    changed = context.model_copy(update={"evidence": (ref,)})
    result = controller(workflow_fixture).check_and_release(candidate, changed, checker=lambda *_: PASSED, current_context=lambda: changed)
    assert result.reason == "REQUIRED_EVIDENCE_INCOMPLETE" and result.checked_bytes is None
    # A completed empty Search is legitimate evidence-tool output, not recommendation support.
    pack = app.state.tools.search(SearchInput(query="nohitunlikely"))
    app.state.tools.complete(CompleteInput(runId=pack["runId"]))
    run = app.state.tools.repository.get(pack["runId"])
    ref = ref.model_copy(update={"run_id": run.id, "result_digest": run.result_digest})
    changed = context.model_copy(update={"evidence": (ref,)})
    result = controller(workflow_fixture).check_and_release(candidate, changed, checker=lambda *_: PASSED, current_context=lambda: changed)
    assert result.reason == "EVIDENCE_MISSING"
    assert_isolated(workflow_fixture, result)


@pytest.mark.parametrize("expanded", [False, True])
def test_actual_windowed_search_and_read_cannot_satisfy_required_evidence(workflow_fixture, expanded):
    app, context, candidate, source = workflow_fixture
    source.write_text("# Foundation\n" + "apples " * 2000, encoding="utf8")
    tools = app.state.tools
    tools.index("kb").build()
    pack = tools.search(SearchInput(query="apples"))
    tools.complete(CompleteInput(runId=pack["runId"]))
    if expanded:
        pack = tools.read(ReadInput(searchRunId=pack["runId"], evidenceIds=[pack["evidence"][0]["evidenceId"]]))
        tools.complete(CompleteInput(runId=pack["runId"]))
    assert pack["evidence"][0]["windowed"] is True
    run = tools.repository.get(pack["runId"])
    reference = EvidenceReference(runId=run.id, resultDigest=run.result_digest,
        requiredEvidenceIds=tuple(item["evidenceId"] for item in run.pack["evidence"]))
    changed = context.model_copy(update={"evidence": (reference,)})
    def forbidden(*_):
        pytest.fail("Windowed required evidence reached the checker.")
    outcome = controller(workflow_fixture).check_and_release(candidate, changed,
        checker=forbidden, current_context=lambda: changed)
    assert outcome.checked_bytes is None and outcome.reason == "REQUIRED_EVIDENCE_INCOMPLETE"
    assert_isolated(workflow_fixture, outcome)


@pytest.mark.parametrize("with_monthly_report", [False, True])
def test_fc_required_workflow_evidence_must_be_whole_reports(tmp_path, fc_archive, monkeypatch, with_monthly_report):
    state = tmp_path / "state"
    state.mkdir()
    install_fc(fc_archive, state)
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "synthetic-token")
    record_ids = ["entry:one", "monthly-review:2025-03"] if with_monthly_report else ["entry:one"]
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", canonical_json({"synthetic": record_ids}))
    app = create_app(state, "x" * 64)
    tools = app.state.tools
    record = {"id": "one", "date": "2025-03-01", "postings": [
        {"accountId": "a" * 64, "side": "debit" if index % 2 else "credit", "units": "1", "commodityCode": "CNY"}
        for index in range(120)]}
    record["postings"][-1]["accountId"] = "synthetic-required-tail"

    def serve(request):
        assert request.method == "GET"
        if request.url.path == "/api/v3/health":
            data = {"status": "ok", "service": "finance-core", "apiVersion": "3.9.0"}
        elif request.url.path == "/api/v3/workspaces":
            data = {"data": [{"id": "synthetic", "status": "active"}]}
        elif request.url.path == "/api/v3/workspaces/synthetic/reports/monthly-review":
            data = {"workspaceId": "synthetic", "readOnly": True, "data": {
                "schemaVersion": 1, "calculationVersion": "monthly-review-v1", "month": "2025-03",
                "windowStart": "2025-01-01", "windowEndExclusive": "2025-04-01", "status": "ready",
                "revision": fingerprint("synthetic empty completed months"),
                "months": [{"month": month, "postedEntryCount": 0, "reversalEntryCount": 0,
                    "otherCategoryPostingCount": 0, "currencies": []} for month in ("2025-01", "2025-02", "2025-03")],
                "coverage": {"ledgerCalculation": "complete", "externalCompleteness": "unknown",
                    "accountClassification": "current-account-definitions", "invalidDateEntryCount": 0}}}
        else:
            assert request.url.path == "/api/v3/workspaces/synthetic/journal-entries/one"
            data = {"workspaceId": "synthetic", "data": record}
        return httpx.Response(200, json=data)

    monkeypatch.setitem(tools.fc.read_evidence.__globals__, "_client", lambda base, token: httpx.Client(
        base_url=base, headers={"authorization": "Bearer " + token}, transport=httpx.MockTransport(serve)))
    try:
        tools.repository.save_profile(SourceProfile(id="finance-core", kind="fc", approved=True))
        pack = tools.fc_read(FcInput(operation="read", workspaceId="synthetic", recordIds=record_ids))
        tools.complete(CompleteInput(runId=pack["runId"]))
        assert "synthetic-required-tail" not in pack["evidence"][0]["text"]
        run = tools.repository.get(pack["runId"])
        context = SyntheticContext(evidence=(EvidenceReference(runId=run.id, resultDigest=run.result_digest,
            requiredEvidenceIds=tuple(pack["requiredEvidenceIds"] if with_monthly_report else
                [item["evidenceId"] for item in pack["evidence"]])),),
            planRevision=fingerprint("synthetic plan"), constraintsRevision=fingerprint("synthetic constraints"),
            financialFoundationComplete=True)
        gate = SyntheticRecommendationWorkflow(app.state.workflows, tools, enabled=True)
        candidate = PrivateCandidate(b"synthetic private proposal")
        result = gate.check_and_release(candidate, context,
            checker=lambda *_: PASSED, current_context=lambda: context)
        if with_monthly_report:
            assert result.reason is None and result.checked_bytes == candidate.body
        else:
            assert result.reason == "REQUIRED_EVIDENCE_INCOMPLETE" and result.checked_bytes is None
        assert tools.repository.get(run.id) == run
    finally:
        tools.repository.close()


def test_cancel_can_win_over_private_check_return(workflow_fixture):
    gate = controller(workflow_fixture)
    entered, resume = Event(), Event()
    def check(*_):
        entered.set()
        assert resume.wait(5)
        return PASSED
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(release, gate, workflow_fixture, checker=check)
        assert entered.wait(5)
        cancelled = gate.cancel()
        resume.set()
        result = pending.result(timeout=5)
    assert cancelled.receipt.status == "cancelled"
    assert result.checked_bytes is None and result.receipt.status == "cancelled"
    assert_isolated(workflow_fixture, result)


def test_conflicting_completion_and_cancel_after_release(workflow_fixture):
    gate = controller(workflow_fixture)
    entered, resume = Event(), Event()
    def check(*_):
        entered.set()
        assert resume.wait(5)
        return PASSED
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(release, gate, workflow_fixture, checker=check)
        assert entered.wait(5)
        conflicting = release(gate, workflow_fixture)
        resume.set()
        result = pending.result(timeout=5)
    assert conflicting.checked_bytes is None and result.checked_bytes is None
    gate = controller(workflow_fixture)
    checked = release(gate, workflow_fixture)
    assert checked.checked_bytes is not None
    assert gate.cancel().reason == "STATE_CONFLICT"
    assert gate.store.get(checked.receipt.id).status == "checked"


@pytest.mark.parametrize("stage", ["creation", "checking", "finished"])
def test_persistence_failure_refuses_before_release(workflow_fixture, monkeypatch, stage):
    app, *_ = workflow_fixture
    original = app.state.workflows.save
    def save(receipt, **options):
        if stage == "creation" or receipt.stage == stage:
            raise OSError(workflow_fixture[2].body.decode())
        return original(receipt, **options)
    monkeypatch.setattr(app.state.workflows, "save", save)
    result = release(controller(workflow_fixture), workflow_fixture)
    assert result.checked_bytes is None and result.reason == "PERSISTENCE_FAILED"
    assert_isolated(workflow_fixture, result)


@pytest.mark.parametrize("slow_stage", ["check", "commit"])
def test_timeout_and_late_success_cannot_release(workflow_fixture, monkeypatch, slow_stage):
    app, *_ = workflow_fixture
    clock = Clock()
    gate = controller(workflow_fixture, clock=clock)
    original = app.state.workflows.save
    def save(receipt, **options):
        result = original(receipt, **options)
        if slow_stage == "commit" and receipt.status == "checked":
            clock.value = 600
        return result
    monkeypatch.setattr(app.state.workflows, "save", save)
    def check(*_):
        if slow_stage == "check":
            clock.value = 600
        return PASSED
    result = release(gate, workflow_fixture, checker=check)
    assert result.reason == "DEADLINE_EXCEEDED" and result.checked_bytes is None
    assert result.receipt.status == "refused"
    assert_isolated(workflow_fixture, result)


def test_deadline_expired_during_final_context_read_cannot_release(workflow_fixture):
    app, context, _, _ = workflow_fixture
    clock = Clock()
    gate = controller(workflow_fixture, clock=clock)

    def current_context():
        if app.state.workflows.receipts()[0].status == "checked":
            clock.value = 600
        return context

    result = release(gate, workflow_fixture, current_context=current_context)
    assert result.reason == "DEADLINE_EXCEEDED" and result.checked_bytes is None
    assert app.state.workflows.get(result.receipt.id).status == "refused"
    assert_isolated(workflow_fixture, result)


def test_candidate_changed_during_final_context_read_requires_rechecking(workflow_fixture):
    app, context, candidate, _ = workflow_fixture
    gate = controller(workflow_fixture)

    def current_context():
        if app.state.workflows.receipts()[0].status == "checked":
            candidate.body = b"synthetic post-check rewrite"
        return context

    result = release(gate, workflow_fixture, current_context=current_context)
    assert result.reason == "RESULT_CHANGED" and result.checked_bytes is None
    assert app.state.workflows.get(result.receipt.id).status == "refused"
    assert_isolated(workflow_fixture, result)


def test_unknown_usage_or_unsettled_requests_refuse(workflow_fixture):
    gate = controller(workflow_fixture)
    key = gate.reserve(1200, 300)
    result = gate.reconcile(key)
    assert result.reason == "USAGE_UNKNOWN"
    assert result.receipt.budget.input_tokens == 1200
    assert result.receipt.budget.output_tokens == 300
    assert release(gate, workflow_fixture).checked_bytes is None
    pending = controller(workflow_fixture)
    pending.reserve(100, 100)
    result = release(pending, workflow_fixture)
    assert result.reason == "REQUESTS_PENDING" and result.checked_bytes is None
    assert_isolated(workflow_fixture, result)


def test_remediation_is_explicit_changed_and_shares_previous_cost(workflow_fixture):
    app, context, candidate, _ = workflow_fixture
    gate = controller(workflow_fixture)
    key = gate.reserve(1000, 1000)
    gate.reconcile(key, input_tokens=900, output_tokens=500, charge_micro_cny=6800)
    failed = PASSED.model_copy(update={"numbers": "failed"})
    first = release(gate, workflow_fixture, checker=lambda *_: failed, allow_remediation=True)
    assert first.receipt.status == "active" and first.receipt.stage == "remediation"
    changed = context.model_copy(update={"constraints_revision": fingerprint("corrected synthetic calculation inputs")})
    assert gate.remediate(changed).reason is None
    key = gate.reserve(2000, 1000)
    gate.reconcile(key, input_tokens=1800, output_tokens=900, charge_micro_cny=12600)
    checked = gate.check_and_release(candidate, changed, checker=lambda *_: PASSED, current_context=lambda: changed)
    assert checked.checked_bytes == candidate.body
    assert checked.receipt.budget.input_tokens == 2700
    assert checked.receipt.budget.liability_micro_cny == 19400
    assert checked.receipt.budget.remediation_rounds == 1
    unchanged = controller(workflow_fixture)
    release(unchanged, workflow_fixture, checker=lambda *_: failed, allow_remediation=True)
    assert unchanged.remediate(context).reason == "REPEATED_FAILURE"


def test_crash_recovery_does_not_replay_or_rewrite_evidence(workflow_fixture):
    app, context, _, _ = workflow_fixture
    gate = controller(workflow_fixture)
    pending = app.state.workflows.receipts()[0]
    run = app.state.tools.repository.get(context.evidence[0].run_id)
    gate.reserve(1000, 500)
    recovered = WorkflowStore(app.state.tools.repository)
    assert recovered.get(pending.id).status == "interrupted"
    assert recovered.get(pending.id).reason_code == "INTERRUPTED_UNKNOWN"
    assert recovered.get(pending.id).budget.liability_micro_cny == 7000
    assert app.state.tools.repository.get(run.id) == run
    assert release(gate, workflow_fixture).checked_bytes is None


def test_disabled_has_no_receipt_or_effect_on_evidence(workflow_fixture):
    app, _, candidate, _ = workflow_fixture
    runs = app.state.tools.repository.runs()
    disabled = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools)
    outcome = release(disabled, workflow_fixture)
    assert outcome.reason == "FEATURE_DISABLED" and outcome.checked_bytes is None
    assert not app.state.workflows.receipts() and app.state.tools.repository.runs() == runs


def test_diagnostic_allowlist_rejects_free_text_and_forged_instances(workflow_fixture):
    app, *_ = workflow_fixture
    controller(workflow_fixture)
    saved = app.state.workflows.receipts()[0]
    body = saved.model_dump(by_alias=True)
    for extra in ("draft", "summary", "exception", "adopted", "nativeTranscript"):
        with pytest.raises(ValidationError):
            WorkflowReceipt.model_validate({**body, extra: workflow_fixture[2].body.decode()})
    with pytest.raises(ValidationError):
        WorkflowReceipt.model_validate({**body, "reasonCode": workflow_fixture[2].body.decode()})
    with pytest.raises(ValidationError):
        app.state.workflows.save(saved.model_copy(update={"id": workflow_fixture[2].body.decode()}), expected_revision=saved.revision)


def test_shared_reservations_are_atomic_and_never_per_request():
    budget = WorkflowBudget()
    def reserve(_):
        try:
            return budget.reserve(25_000, 12_500)
        except BudgetRejected as error:
            return error.reason
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert results.count("TOKEN_LIMIT") == 4
    snapshot = budget.snapshot()
    assert (snapshot.input_tokens, snapshot.output_tokens, snapshot.liability_micro_cny) == (100_000, 50_000, 700_000)


def test_cost_fee_unknown_usage_and_model_are_conservative():
    budget = WorkflowBudget(tariff=SyntheticTariff(request_fee_micro_cny=800_000))
    key = budget.reserve(10, 10)
    with pytest.raises(BudgetRejected, match="COST_LIMIT"):
        budget.reserve(10, 10)
    with pytest.raises(BudgetRejected, match="USAGE_UNKNOWN"):
        budget.reconcile(key)
    assert budget.snapshot().liability_micro_cny == 800_120
    with pytest.raises(BudgetRejected, match="USAGE_UNKNOWN"):
        budget.reserve(1, 1)
    with pytest.raises(BudgetRejected, match="MODEL_MISMATCH"):
        WorkflowBudget().reserve(1, 1, model="different-model")
    with pytest.raises(BudgetRejected, match="TOKEN_LIMIT"):
        WorkflowBudget().reserve(True, 1)
    budget = WorkflowBudget()
    key = budget.reserve(10, 10)
    with pytest.raises(BudgetRejected, match="USAGE_EXCEEDED_RESERVATION"):
        budget.reconcile(key, input_tokens=10, output_tokens=11, charge_micro_cny=130)
    assert budget.snapshot().output_tokens == 10 and budget.snapshot().usage_unknown


def test_remediation_deadline_and_repeated_failure_never_reset_budget():
    clock = Clock()
    budget = WorkflowBudget(clock=clock)
    key = budget.reserve(100, 100)
    budget.reconcile(key, input_tokens=100, output_tokens=100, charge_micro_cny=1200)
    for index in range(2):
        budget.note_failure("NUMBERS_CHECK_FAILED", fingerprint(str(index)))
        budget.remediate(fingerprint(str(index + 1)))
    budget.note_failure("NUMBERS_CHECK_FAILED", fingerprint("2"))
    with pytest.raises(BudgetRejected, match="REMEDIATION_EXHAUSTED"):
        budget.remediate(fingerprint("3"))
    assert budget.snapshot().liability_micro_cny == 1200 and budget.snapshot().attempts == 3
    clock.value = 600
    with pytest.raises(BudgetRejected, match="DEADLINE_EXCEEDED"):
        budget.reserve(1, 1)
