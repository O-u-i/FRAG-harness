"""Opt-in synthetic gate only. No production carrier, model call or chat interception."""
from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4

from frag_api.repositories.workflow_store import utc_now
from frag_api.request_spec import fingerprint
from frag_api.schemas.workflow import CheckResult, SyntheticContext, WorkflowReceipt
from frag_api.services.workflow_budget import BudgetRejected, WorkflowBudget


class PrivateCandidate:
    """Volatile internal bytes; not an ApiModel, tool input, receipt or log message."""
    __slots__ = ("body",)

    def __init__(self, body: bytes):
        if type(body) is not bytes or not body or len(body) > 16 * 1024:
            raise ValueError("Invalid synthetic candidate.")
        self.body = body

    def __repr__(self):
        return "<PrivateCandidate>"


@dataclass(frozen=True)
class SyntheticOutcome:
    receipt: WorkflowReceipt | None
    reason: str | None = None
    checked_bytes: bytes | None = field(default=None, repr=False)


class SyntheticRecommendationWorkflow:
    """Each instance is a single bounded workflow; enable only in synthetic tests.

    The app never constructs this controller and exposes no candidate/check API.
    Context assertions and checker callbacks do NOT implement financial advice quality.
    """
    def __init__(self, store, tools, *, enabled=False, clock=None, tariff=None):
        self.store, self.tools = store, tools
        self._lock = RLock()
        self._enabled = enabled is True
        self._finished = not self._enabled
        self._failed_persistence = False
        self._budget = WorkflowBudget(**({"clock": clock} if clock else {}), tariff=tariff)
        self._context = None
        self._receipt = None
        if self._enabled:
            now = utc_now()
            self._receipt = WorkflowReceipt(id=uuid4().hex, revision=1, createdAt=now, updatedAt=now,
                status="active", stage="evidence", budget=self._budget.snapshot())
            try:
                self.store.save(self._receipt)
            except Exception:
                self._failed_persistence = self._finished = True
                self._budget.stop()

    def _outcome(self, reason=None, body=None):
        return SyntheticOutcome(self._receipt if not self._failed_persistence else None, reason, body)

    def _available(self):
        if not self._enabled:
            return self._outcome("FEATURE_DISABLED")
        if self._failed_persistence:
            return self._outcome("PERSISTENCE_FAILED")
        if self._finished:
            return self._outcome("STATE_CONFLICT")
        return None

    def _save(self, *, revoke_unreleased=False, **changes):
        old = self._receipt
        value = WorkflowReceipt.model_validate({**old.model_dump(by_alias=True), **changes,
            "revision": old.revision + 1, "updatedAt": utc_now(), "budget": self._budget.snapshot()})
        try:
            self.store.save(value, expected_revision=old.revision, revoke_unreleased=revoke_unreleased)
        except Exception:
            self._failed_persistence = self._finished = True
            self._budget.stop()
            return False
        self._receipt = value
        return True

    def _refuse(self, reason, *, status="refused", revoke_unreleased=False):
        self._finished = True
        self._save(status=status, stage="finished", reasonCode=reason, revoke_unreleased=revoke_unreleased)
        self._budget.stop()  # Outstanding/unknown liability is deliberately retained.
        return self._outcome("PERSISTENCE_FAILED" if self._failed_persistence else reason)

    def reserve(self, complete_input_tokens, max_counted_output_tokens, **options):
        with self._lock:
            unavailable = self._available()
            if unavailable:
                return unavailable
            if self._receipt.stage == "remediation":
                return self._refuse("STATE_CONFLICT")
            try:
                key = self._budget.reserve(complete_input_tokens, max_counted_output_tokens, **options)
            except BudgetRejected as error:
                return self._refuse(error.reason)
            if not self._save(stage="checking" if self._receipt.stage == "checking" else "drafting"):
                return self._outcome("PERSISTENCE_FAILED")
            return key  # Synthetic reservation, never an actual provider request.

    def reconcile(self, key, **usage):
        with self._lock:
            unavailable = self._available()
            if unavailable:
                return unavailable
            try:
                self._budget.reconcile(key, **usage)
            except BudgetRejected as error:
                return self._refuse(error.reason)
            self._save()
            return self._outcome("PERSISTENCE_FAILED" if self._failed_persistence else None)

    def cancel(self):
        with self._lock:
            return self._available() or self._refuse("CANCELLED", status="cancelled")

    def interrupt(self):
        with self._lock:
            return self._available() or self._refuse("INTERRUPTED_UNKNOWN", status="interrupted")

    def remediate(self, context):
        with self._lock:
            unavailable = self._available()
            if unavailable:
                return unavailable
            if self._receipt.stage != "remediation":
                return self._refuse("STATE_CONFLICT")
            try:
                context = SyntheticContext.model_validate(context.model_dump(by_alias=True))
                self._budget.remediate(fingerprint(context.model_dump(by_alias=True)))
            except BudgetRejected as error:
                return self._refuse(error.reason)
            except Exception:
                return self._refuse("CHECK_UNKNOWN")
            self._context = context
            self._save(stage="evidence", reasonCode=None)
            return self._outcome("PERSISTENCE_FAILED" if self._failed_persistence else None)

    def _evidence_reason(self, context):
        if not context.evidence:
            return "EVIDENCE_MISSING"
        if not context.plan_revision:
            return "PLAN_MISSING"
        if not context.constraints_revision:
            return "CONSTRAINTS_MISSING"
        if not context.financial_foundation_complete:
            return "FINANCIAL_FOUNDATION_MISSING"
        for reference in context.evidence:
            run = self.tools.repository.get(reference.run_id)
            if (run.status != "completed" or not run.pack or not run.source_bindings or not run.pack.get("evidence")
                    or run.result_digest != reference.result_digest or fingerprint(run.pack) != reference.result_digest):
                return "EVIDENCE_MISSING"
            items = {item["evidenceId"]: item for item in run.pack["evidence"]}
            required = set(reference.required_evidence_ids) | set(run.pack.get("requiredEvidenceIds", []))
            if not required.issubset(items) or any(items[key].get("windowed", False) for key in required):
                return "REQUIRED_EVIDENCE_INCOMPLETE"
            # The pinned reader attests whole monthly reports, not its bounded journal summaries.
            if run.tool == "frag_fc_read" and any(not items[key].get("locatorId", "").startswith("monthly-review:") for key in required):
                return "REQUIRED_EVIDENCE_INCOMPLETE"
            self.tools.validate_current(run)
        return None

    @staticmethod
    def _checks_reason(checks):
        if "unknown" in checks.model_dump().values():
            return "CHECK_UNKNOWN"
        for name, reason in (("evidence", "EVIDENCE_MISSING"), ("numbers", "NUMBERS_CHECK_FAILED"),
                ("constraints", "CONSTRAINTS_CHECK_FAILED"), ("reasoning", "REASONING_CHECK_FAILED"),
                ("suitability", "SUITABILITY_CHECK_FAILED")):
            if getattr(checks, name) != "passed":
                return reason
        return None

    def check_and_release(self, candidate, context, *, checker, current_context, allow_remediation=False):
        """Only the exact checked bytes can leave this synthetic boundary, after commit."""
        with self._lock:
            unavailable = self._available()
            if unavailable:
                return unavailable
            if self._receipt.stage not in {"evidence", "drafting"}:
                return self._refuse("STATE_CONFLICT")
            try:
                self._budget.ready()
                context = SyntheticContext.model_validate(context.model_dump(by_alias=True))
                if self._context is not None and context != self._context:
                    return self._refuse("CONTEXT_CHANGED")
                if type(candidate) is not PrivateCandidate:
                    return self._refuse("CHECK_UNKNOWN")
                body = candidate.body
                if type(body) is not bytes or not body or len(body) > 16 * 1024:
                    return self._refuse("CHECK_UNKNOWN")
                reason = self._evidence_reason(context)
                if reason:
                    return self._refuse(reason)
            except BudgetRejected as error:
                return self._refuse(error.reason)
            except Exception:
                return self._refuse("EVIDENCE_STALE")
            self._context = context
            if not self._save(stage="checking", evidence=context.evidence, planRevision=context.plan_revision,
                    constraintsRevision=context.constraints_revision):
                return self._outcome("PERSISTENCE_FAILED")
        # Do not hold the lifecycle lock over private checks: cancellation can win.
        reason = None
        try:
            result = checker(body, context)
            checks = CheckResult.model_validate(result.model_dump(by_alias=True))
            reason = self._checks_reason(checks)
            latest = current_context()
            latest = SyntheticContext.model_validate(latest.model_dump(by_alias=True))
        except Exception:
            reason, latest = "CHECK_EXCEPTION", None
        with self._lock:
            unavailable = self._available()
            if unavailable:
                return unavailable
            try:
                self._budget.ready()
                if candidate.body != body:
                    return self._refuse("RESULT_CHANGED")
                if latest != context and latest is not None:
                    return self._refuse("CONTEXT_CHANGED")
                if reason:
                    if allow_remediation is True and reason in {"EVIDENCE_MISSING", "NUMBERS_CHECK_FAILED", "REASONING_CHECK_FAILED"}:
                        self._budget.note_failure(reason, fingerprint(context.model_dump(by_alias=True)))
                        self._save(stage="remediation", reasonCode=reason)
                        return self._outcome("PERSISTENCE_FAILED" if self._failed_persistence else reason)
                    return self._refuse(reason)
                reason = self._evidence_reason(latest)
                if reason:
                    return self._refuse(reason)
            except BudgetRejected as error:
                return self._refuse(error.reason)
            except Exception:
                return self._refuse("EVIDENCE_STALE")
            if not self._save(stage="finished", status="checked", reasonCode="CHECKS_PASSED"):
                return self._outcome("PERSISTENCE_FAILED")
            # A slow commit must not release a result beyond the whole-workflow deadline.
            try:
                self._budget.ready()
                final_context = current_context()
                final_context = SyntheticContext.model_validate(final_context.model_dump(by_alias=True))
                if final_context != context:
                    return self._refuse("CONTEXT_CHANGED", revoke_unreleased=True)
                reason = self._evidence_reason(final_context)
                if reason:
                    return self._refuse(reason, revoke_unreleased=True)
                if candidate.body != body:
                    return self._refuse("RESULT_CHANGED", revoke_unreleased=True)
                # Final context/source reads also consume the whole-workflow deadline.
                self._budget.ready()
            except BudgetRejected as error:
                return self._refuse(error.reason, revoke_unreleased=True)
            except Exception:
                return self._refuse("EVIDENCE_STALE", revoke_unreleased=True)
            self._finished = True
            self._budget.stop()
            return self._outcome(body=body)
