"""Single lifecycle owner for persisted snapshots, dispatches, checkpoints and review."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import time
from collections import OrderedDict
from threading import RLock
from pydantic import ValidationError

from frag_api.errors import RuntimeConflictError, RequestBudgetError
from frag_api.repositories.runtime_repository import RuntimeRepository
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.governance import PreparedCall
from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer
from frag_api.request_spec import estimated_tokens, fingerprint
from frag_api.schemas.runtime import (
    AttemptRecord, ReviewRecord, ReviewRequest, RevisionRecord, RevisionRequest,
    RunRecord, RunReport, SelectionSnapshot, SessionRecord,
)
from frag_api.services.runtime_policy import HostPolicy, redact_value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier() -> str:
    return uuid4().hex


def durable_value(value, secrets=()):
    if hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True)
    if isinstance(value, dict):
        prohibited = {"apikey", "approvaltoken", "authorization", "headers", "accesstoken"}
        return {key: durable_value(item, secrets) for key, item in value.items()
                if key.lower().replace("_", "").replace("-", "") not in prohibited}
    if isinstance(value, (tuple, list)):
        return [durable_value(item, secrets) for item in value]
    return redact_value(value, secrets)


class RuntimeService:
    def __init__(self, repository: RuntimeRepository):
        self.repository = repository
        self.repository.recover_dispatches(now())
        self.secret_values: tuple[str, ...] = ()
        self._approval_secrets: OrderedDict[str, float] = OrderedDict()
        self._secret_lock = RLock()
        self._restore_completed()

    def remember_approval(self, token):
        with self._secret_lock:
            self._approval_secrets[token] = time.monotonic() + 600

    @property
    def redaction_secrets(self):
        with self._secret_lock:
            stamp = time.monotonic()
            while self._approval_secrets and next(iter(self._approval_secrets.values())) <= stamp:
                self._approval_secrets.popitem(last=False)
            return self.secret_values + tuple(self._approval_secrets)

    def close(self):
        with self._secret_lock:
            self.secret_values = ()
            self._approval_secrets.clear()

    def _restore_completed(self):
        # A committed response is a known result: finish only deterministic host checks.
        for report in self.repository.incomplete_returns():
            for call in report.requests:
                if call.status != "completed" or call.structural_validation != "UNDETERMINED":
                    continue
                try:
                    if call.output_digest and call.output_digest != fingerprint(call.output):
                        raise ValueError()
                    if call.stage == "context":
                        output = RagContextCompression.model_validate(call.output)
                        allowed = {e.evidence_id for e in report.selection.candidate_evidence}
                        ids = [e.evidence_id for e in output.evidence]
                        valid = set(ids) == allowed and len(ids) == len(allowed) and estimated_tokens(output.model_dump(by_alias=True)) <= 1500
                    else:
                        output = RagGroundedAnswer.model_validate(call.output)
                        allowed = {e.evidence_id for e in report.context.evidence} if report.context else set()
                        cited = {e for c in output.claims for e in c.evidence_ids}
                        valid = bool(cited) and cited.issubset(allowed) and estimated_tokens(output.model_dump(by_alias=True)) <= 2000
                    if not valid or report.consumed_tokens > report.run_token_limit:
                        raise ValueError()
                except (ValidationError, ValueError):
                    self.failure(report.run.id, call.id, "INVALID_PERSISTED_OUTPUT")
                    continue
                self.checkpoint(report.run.id, call.id, output, stage=call.stage)

    def create_session(self, title="Evidence review") -> SessionRecord:
        return self.repository.create_session(SessionRecord(id=identifier(), title=durable_value(title, self.redaction_secrets), createdAt=now()))

    def start(self, kind, source_request, preview) -> tuple[str, str, str]:
        parent_id = source_request.parent_run_id
        if parent_id:
            parent = self.repository.get(parent_id)
            if parent.run.kind != kind or (source_request.session_id and source_request.session_id != parent.run.session_id):
                raise RuntimeConflictError()
            session = parent.session
        else:
            session = self.repository.session(source_request.session_id) if source_request.session_id else self.create_session()
        stamp, run_id, call_id = now(), identifier(), identifier()
        prepared = PreparedCall.model_validate(durable_value(preview.prepared_call, self.redaction_secrets))
        snapshot = SelectionSnapshot(
            goal=preview.goal if kind == "harness" else preview.query,
            sourceBindings=preview.source_bindings, candidateEvidence=preview.candidate_evidence,
            task=preview.task, input=durable_value(source_request, self.redaction_secrets),
        )
        snapshot = SelectionSnapshot.model_validate(durable_value(snapshot, self.redaction_secrets))
        report = RunReport(
            snapshotDigest=fingerprint(snapshot.model_dump(by_alias=True)),
            session=session, run=RunRecord(id=run_id, sessionId=session.id, parentRunId=parent_id,
                kind=kind, status="ready_context" if preview.can_approve else "paused",
                createdAt=stamp, updatedAt=stamp, version=1, activeCallId=call_id),
            selection=snapshot, requests=[AttemptRecord(id=call_id, stage="context", status="prepared", preparedCall=prepared, createdAt=stamp)],
            context=None, modelOutput=None, reviews=[], revisions=[], consumedTokens=0,
            runTokenLimit=prepared.run_token_limit, structuralValidation="NOT_RUN", semanticReview="NOT_RUN",
            limitations=["Source quality fields describe known metadata; they do not verify factual truth.",
                         "Schema and citation membership checks do not establish semantic support.",
                         "Automatic redaction cannot identify every private value.",
                         "Input tokens are estimates when provider usage is unavailable."],
        )
        self.repository.create(report)
        return run_id, session.id, call_id

    def prepare(self, run_id, prepared, stage, *, allow_paused=False) -> str:
        call_id = identifier()
        safe_call = PreparedCall.model_validate(durable_value(prepared, self.redaction_secrets))
        def change(report):
            if (report.run.status in ("outcome_unknown", "accepted", "rejected")
                    or (report.run.status == "paused" and not allow_paused)
                    or any(c.status == "dispatching" or (c.status == "completed" and c.structural_validation == "UNDETERMINED") for c in report.requests)):
                raise RuntimeConflictError()
            if allow_paused and report.reviews:
                HostPolicy.require_task(report.reviews[-1].checklist)
            reservation = prepared.estimated_input_tokens + prepared.request_body()["max_output_tokens"]
            if report.consumed_tokens + reservation > report.run_token_limit:
                raise RequestBudgetError()
            report.requests.append(AttemptRecord(id=call_id, stage=stage, status="prepared", preparedCall=safe_call, createdAt=now()))
            report.run.status = "ready_context" if stage == "context" else "awaiting_inference"
            report.run.active_call_id, report.run.updated_at = call_id, now()
        self.repository.update(run_id, change)
        return call_id

    def claim(self, run_id, call_id, prepared):
        def change(report):
            expected = "ready_context" if prepared.purpose == "context" else "awaiting_inference"
            if report.run.status != expected or report.run.active_call_id != call_id:
                raise RuntimeConflictError()
            call = next(c for c in report.requests if c.id == call_id)
            if call.status != "prepared" or call.prepared_call.fingerprint != prepared.fingerprint:
                raise RuntimeConflictError()
            reservation = prepared.estimated_input_tokens + prepared.request_body()["max_output_tokens"]
            if report.consumed_tokens + reservation > report.run_token_limit:
                raise RequestBudgetError()
            call.status = "dispatching"
            report.consumed_tokens += reservation
            report.run.updated_at = now()
        self.repository.update(run_id, change)

    def returned(self, run_id, call_id, output, usage: ProviderUsage):
        safe_output = durable_value(output, self.redaction_secrets)
        def change(report):
            call = next(c for c in report.requests if c.id == call_id)
            if call.status != "dispatching":
                raise RuntimeConflictError()
            call.status, call.finished_at = "completed", now()
            call.output, call.usage, call.structural_validation = safe_output, usage, "UNDETERMINED"
            call.output_digest = fingerprint(safe_output)
            prepared = call.prepared_call
            reservation = prepared.estimated_input_tokens + prepared.request_body()["max_output_tokens"]
            count = (usage.input_tokens if usage.input_tokens is not None else prepared.estimated_input_tokens) + (usage.output_tokens if usage.output_tokens is not None else prepared.request_body()["max_output_tokens"])
            report.consumed_tokens += count - reservation
            report.run.updated_at = now()
        self.repository.update(run_id, change)

    def failure(self, run_id, call_id, code, *, unknown=False):
        def change(report):
            call = next(c for c in report.requests if c.id == call_id)
            call.status = "outcome_unknown" if unknown else "failed"
            outcome = "FAIL" if code in ("INVALID_LLM_OUTPUT", "INVALID_PERSISTED_OUTPUT") else "ERROR"
            call.error_code, call.finished_at, call.structural_validation = code, now(), outcome
            if unknown:
                report.run.status = "outcome_unknown"
            elif report.run.status not in ("paused", "rejected"):
                report.run.status = "error"
            report.run.active_call_id, report.run.updated_at = None, now()
            report.structural_validation = outcome
        self.repository.update(run_id, change)

    def checkpoint(self, run_id, call_id, output, *, stage):
        safe = durable_value(output, self.redaction_secrets)
        def change(report):
            call = next(c for c in report.requests if c.id == call_id)
            if call.status != "completed":
                raise RuntimeConflictError()
            call.structural_validation = "PASS"
            controlled = report.run.status in ("paused", "rejected")
            if stage == "context":
                report.context = RagContextCompression.model_validate(safe)
                if not controlled:
                    report.run.status = "awaiting_inference"
            else:
                report.model_output = RagGroundedAnswer.model_validate(safe)
                if not controlled:
                    report.run.status = "awaiting_review"
                report.structural_validation = "PASS"
            report.run.active_call_id, report.run.updated_at = None, now()
        self.repository.update(run_id, change)

    def review(self, run_id, request: ReviewRequest) -> RunReport:
        def change(report):
            if request.decision == "accepted" and any(c.status == "dispatching" for c in report.requests):
                raise RuntimeConflictError()
            original = [(c.id, c.text, c.blocking) for c in report.selection.task.checklist]
            incoming = [(c.id, c.text, c.blocking) for c in request.checklist.checklist]
            if original != incoming:
                raise RuntimeConflictError()
            revision = next((r for r in report.revisions if r.id == request.target), None)
            if request.target != "model" and revision is None:
                raise RuntimeConflictError()
            if request.decision == "accepted" and (report.model_output is None or report.run.status == "outcome_unknown"):
                raise RuntimeConflictError()
            decision = "paused" if request.decision == "accepted" and request.checklist.blocking_ids else request.decision
            note = request.note
            if decision != request.decision:
                note = "Acceptance paused: blocking checklist is incomplete. " + note
            review = ReviewRecord(**{**durable_value(request, self.redaction_secrets), "decision":decision, "note":durable_value(note, self.redaction_secrets)}, id=identifier(), createdAt=now())
            report.reviews.append(review)
            if revision:
                revision.review_status = decision
            # A revision's review cannot approve the model original, or vice versa.
            active_target = report.revisions[-1].id if report.revisions else "model"
            if request.target == active_target:
                if report.model_output is not None:
                    report.semantic_review = {"accepted":"PASS", "rejected":"FAIL", "paused":"UNDETERMINED"}[decision]
                if report.run.status != "outcome_unknown":
                    report.run.status = decision
            report.run.updated_at = now()
        return self.repository.update(run_id, change)

    def revise(self, run_id, request: RevisionRequest) -> RunReport:
        def change(report):
            if report.model_output is None or any(c.status == "dispatching" for c in report.requests):
                raise RuntimeConflictError()
            allowed = {e.evidence_id for e in report.context.evidence}
            cited = {e for c in request.result.claims for e in c.evidence_ids}
            if not cited or not cited.issubset(allowed):
                raise RuntimeConflictError()
            values = durable_value(request, self.redaction_secrets)
            revision = RevisionRecord(**values, contentDigest=fingerprint(values["result"]), id=identifier(), createdAt=now())
            report.revisions.append(revision)
            report.semantic_review, report.run.status = "NOT_RUN", "awaiting_review"
            report.run.updated_at = now()
        return self.repository.update(run_id, change)
