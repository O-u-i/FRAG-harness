"""Fixed acceptance set for Slice A. Separate from development/repair cases.

No personal data, provider, native transcript or financial-domain implementation.
These scenarios and expected decisions must not be changed to fit a candidate.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event
from uuid import uuid4
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from frag_api.main import create_app
from frag_api.request_spec import fingerprint
from frag_api.schemas.native import CompleteInput, SearchInput, SourceProfile
from frag_api.schemas.workflow import CheckResult, EvidenceReference, SyntheticContext
from frag_api.services.recommendation_workflow import PrivateCandidate, SyntheticRecommendationWorkflow


@pytest.fixture
def acceptance_case(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    historical = json.dumps({"legacy": "retain without rebinding or replay"})
    with sqlite3.connect(state / "runtime.sqlite3") as db:
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        db.execute("CREATE TABLE agent_sessions (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        for table in ("runs", "agent_sessions"):
            db.execute(f"INSERT INTO {table} VALUES(?,?)", ("historical", historical))
    source = tmp_path / "approved"
    source.mkdir()
    (source / "foundation.md").write_text("# Synthetic foundation\n完整证据 evidence and explicit limits.\n", encoding="utf8")
    app = create_app(state, "x" * 64)
    tools = app.state.tools
    tools.repository.save_profile(SourceProfile(id="kb", root=str(source), approved=True))
    tools.index("kb").build()
    pack = tools.search(SearchInput(query="完整证据 evidence"))
    tools.complete(CompleteInput(runId=pack["runId"]))
    run = tools.repository.get(pack["runId"])
    context = SyntheticContext(evidence=(EvidenceReference(runId=run.id, resultDigest=run.result_digest,
        requiredEvidenceIds=tuple(item["evidenceId"] for item in pack["evidence"])),),
        planRevision=fingerprint("acceptance confirmed plan"), constraintsRevision=fingerprint("acceptance constraints"),
        financialFoundationComplete=True)
    private = PrivateCandidate(("DO-NOT-DISCLOSE-" + uuid4().hex).encode())
    checks = CheckResult(evidence="passed", numbers="passed", constraints="passed", reasoning="passed", suitability="passed")
    try:
        yield app, state, context, private, checks, historical
    finally:
        tools.repository.close()


def visible_surfaces(case, outcome):
    app, state, _, private, _, historical = case
    client = TestClient(app, raise_server_exceptions=False)
    auth = {"authorization": "Bearer " + "x" * 64}
    texts = [repr(outcome), repr(private)]
    for action, body in (("overview", {}), ("run-get", {"runId": outcome.receipt.id}),
            ("memory-candidate", {"runId": outcome.receipt.id, "text": "No workflow receipt is evidence."})):
        response = client.post("/api/manage/" + action, headers=auth, json=body)
        texts.append(response.text)
        if action != "overview":
            assert response.status_code == 404
    for name in ("recommendation", "workflow-check", "workflow-export"):
        texts.append(client.post("/api/tools/" + name, headers=auth, json={"candidate": private.body.decode()}).text)
        texts.append(client.post("/api/manage/" + name, headers=auth, json={"candidate": private.body.decode()}).text)
    overview = client.post("/api/manage/overview", headers=auth, json={}).json()
    assert overview["recommendations"] == {"available": False, "reasonCode": "CARRIER_UNAVAILABLE"}
    assert not overview["memory"]
    assert all(run["tool"] in {"frag_search", "frag_read", "frag_fc_read"} for run in overview["runs"])
    assert all(receipt["kind"] == "recommendation_workflow" and receipt["mode"] == "synthetic" for receipt in overview["workflowReceipts"])
    assert private.body.decode() not in "".join(texts)
    for database in state.rglob("*.sqlite3"):
        assert private.body not in database.read_bytes()
    with app.state.tools.repository.connection() as db:
        for table in ("runs", "agent_sessions"):
            assert db.execute(f"SELECT record FROM {table} WHERE id='historical'").fetchone()[0] == historical


@pytest.mark.parametrize("scenario,expected", [
    ("missing_plan", "PLAN_MISSING"), ("missing_stock_facts", "FINANCIAL_FOUNDATION_MISSING"),
    ("unknown_check", "CHECK_UNKNOWN"), ("exception", "CHECK_EXCEPTION"),
    ("cancelled", "CANCELLED"), ("interrupted", "INTERRUPTED_UNKNOWN"),
    ("stale_constraints", "CONTEXT_CHANGED"), ("timeout", "DEADLINE_EXCEEDED"),
])
def test_fixed_refusal_matrix_and_every_public_surface(acceptance_case, scenario, expected, caplog, capsys):
    app, _, context, private, checks, _ = acceptance_case
    now = [0.0]
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, clock=lambda: now[0])
    latest = context
    if scenario == "missing_plan":
        context = context.model_copy(update={"plan_revision": None})
        latest = context
    if scenario == "missing_stock_facts":
        context = context.model_copy(update={"financial_foundation_complete": False})
        latest = context
    def checker(*_):
        nonlocal latest
        if scenario == "unknown_check":
            return checks.model_copy(update={"evidence": "unknown"})
        if scenario == "exception":
            raise RuntimeError(private.body.decode())
        if scenario == "cancelled":
            gate.cancel()
        if scenario == "interrupted":
            gate.interrupt()
        if scenario == "stale_constraints":
            latest = context.model_copy(update={"constraints_revision": fingerprint("revised")})
        if scenario == "timeout":
            now[0] = 600.0
        return checks
    outcome = gate.check_and_release(private, context, checker=checker, current_context=lambda: latest)
    assert outcome.checked_bytes is None
    assert outcome.receipt.reason_code == expected
    visible_surfaces(acceptance_case, outcome)
    captured = capsys.readouterr()
    assert private.body.decode() not in captured.out + captured.err + caplog.text


def test_checking_api_response_and_cancel_return_race(acceptance_case):
    app, _, context, private, checks, _ = acceptance_case
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True)
    entered, resume = Event(), Event()
    def checker(*_):
        entered.set()
        assert resume.wait(10)
        return checks
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(gate.check_and_release, private, context, checker=checker, current_context=lambda: context)
        assert entered.wait(10)
        response = TestClient(app).post("/api/manage/overview", headers={"authorization": "Bearer " + "x" * 64}, json={})
        assert private.body.decode() not in response.text
        assert response.json()["workflowReceipts"][0]["stage"] == "checking"
        gate.cancel()
        resume.set()
        outcome = future.result(timeout=10)
    assert outcome.checked_bytes is None and outcome.receipt.status == "cancelled"
    visible_surfaces(acceptance_case, outcome)


def test_persistence_failure_never_releases_and_restart_is_unknown_not_replay(acceptance_case, monkeypatch):
    app, state, context, private, checks, _ = acceptance_case
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True)
    save = app.state.workflows.save
    def fail_final(receipt, **options):
        if receipt.status == "checked":
            raise OSError(private.body.decode())
        return save(receipt, **options)
    monkeypatch.setattr(app.state.workflows, "save", fail_final)
    outcome = gate.check_and_release(private, context, checker=lambda *_: checks, current_context=lambda: context)
    assert outcome.checked_bytes is None and outcome.reason == "PERSISTENCE_FAILED" and outcome.receipt is None
    app.state.tools.repository.close()
    restarted = create_app(state, "x" * 64)
    try:
        receipt = restarted.state.workflows.receipts()[0]
        assert receipt.status == "interrupted" and receipt.reason_code == "INTERRUPTED_UNKNOWN"
        response = TestClient(restarted).post("/api/manage/overview", headers={"authorization": "Bearer " + "x" * 64}, json={})
        assert private.body.decode() not in response.text
        assert len(response.json()["runs"]) == 1
    finally:
        restarted.state.tools.repository.close()


def test_exact_release_is_synthetic_not_adoption_and_rollback_retains_evidence(acceptance_case):
    app, _, context, private, checks, _ = acceptance_case
    original = app.state.tools.repository.get(context.evidence[0].run_id)
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: checks, current_context=lambda: context)
    assert sha256(outcome.checked_bytes).hexdigest() == sha256(private.body).hexdigest()
    assert outcome.receipt.status == "checked"
    assert "adopted" not in outcome.receipt.model_dump() and "executed" not in outcome.receipt.model_dump()
    visible_surfaces(acceptance_case, outcome)
    disabled = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools)
    assert disabled.check_and_release(private, context, checker=lambda *_: checks, current_context=lambda: context).reason == "FEATURE_DISABLED"
    assert app.state.tools.repository.get(original.id) == original
    pack = app.state.tools.search(SearchInput(query="完整证据 evidence"))
    assert app.state.tools.complete(CompleteInput(runId=pack["runId"]))["evidence"]
