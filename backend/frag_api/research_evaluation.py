"""Synthetic trajectory fixtures execute the real durable Research runner and KB tools."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from pydantic import RootModel, ValidationError

from frag_api.errors import PolicyRejectedError, RagFingerprintError, RagOutputError, RuntimeConflictError
from frag_api.providers.llm import LlmCallResult, LlmSettings, LlmStageSettings
from frag_api.providers.prepared import verify_prepared
from frag_api.repositories.runtime_repository import RuntimeRepository
from frag_api.research_evaluation_scoring import score_trajectory
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.evaluation import EvalCaseReport, EvalCheck
from frag_api.schemas.harness import HarnessRequest
from frag_api.schemas.research import ResearchDecision
from frag_api.services.cli_executor import ToolExecutionError
from frag_api.services.harness_service import HarnessService
from frag_api.services.kb_tools import KBTools
from frag_api.services.runtime_service import RuntimeService
from frag_api.evaluation_scoring import aggregate


class ScriptedResearchProvider:
    """Fixture decisions are model output data and never bypass the production host."""
    def __init__(self, fixture):
        self.fixture = fixture

    def execute_prepared(self, call):
        fixture = self.fixture
        verify_prepared(call, fixture.settings.research)
        step = fixture.case.steps[len(fixture.calls)]
        report = fixture.runtime.repository.get(fixture.run_id)
        binding = report.selection.source_bindings[0]
        scope = {"identity": binding.identity.model_dump(by_alias=True), "revision": binding.revision,
                 "locatorIds": list(binding.locator_ids)}
        tool_calls = []
        for index in range(step.count if step.action != "finish" else 0):
            call_id = f"eval-turn-{len(fixture.calls) + 1}-tool-{index + 1}"
            arguments = {**scope, "evidenceIds": list(binding.evidence_ids)}
            name = "kb.read"
            if step.action == "search":
                name, arguments = "kb.search", {**scope, "query": step.query, "limit": 10}
            elif step.action == "unknown-tool":
                name = "shell.run"
            elif step.action == "scope-escape":
                arguments["locatorIds"] = ["outside-selected-scope"]
            elif step.action == "malformed-call":
                arguments = None
            elif step.action == "duplicate-call":
                call_id = "duplicate-id"
            tool_calls.append({"callId": call_id, "name": name, **({"arguments": arguments} if arguments is not None else {})})
        observed = list(dict.fromkeys(row.evidence_id for item in report.tool_calls if item.result for row in item.result.evidence))
        payload = {"action": "finish" if step.action == "finish" else "continue", "toolCalls": tool_calls,
                   "evidenceIds": observed if step.action == "finish" else [],
                   "missingInformation": step.missing_information}
        try:
            output = ResearchDecision.model_validate(payload)
        except ValidationError:
            output = RootModel[dict](payload)
        fixture.calls.append((call, payload))
        return LlmCallResult(output, ProviderUsage(inputTokens=120, outputTokens=40))


class ResearchFixture:
    def __init__(self, case, service, workspace):
        self.case, self.rag, self.workspace = case, service, workspace
        self.calls, self.run_id, self.failure_used = [], None, False
        self.repository = RuntimeRepository(workspace / f"research-{uuid4().hex}.sqlite3")
        stage = LlmStageSettings("fake", "offline-scripted-research-v1", None, None, 120)
        self.settings = LlmSettings(context=stage, inference=stage, research=stage)
        self.runtime = None

    def setup(self):
        from frag_api.services.research_flow import ResearchFlow
        if self.runtime is not None:
            self.flow.close()
            for service in (self.harness, self.rag):
                service.approvals.clear()
                service.pending_inference.clear()
                service.flow.runtime = None
            self.runtime.close()
        self.runtime = RuntimeService(RuntimeRepository(self.repository.path))
        self.harness = HarnessService(self.rag.source_service, settings=self.settings)
        self.harness.research_provider = ScriptedResearchProvider(self)
        for kind, service in (("harness", self.harness), ("rag", self.rag)):
            service.flow.runtime, service.flow.kind = self.runtime, kind
        tools = KBTools(self.runtime, self.harness, self.rag)
        if self.case.tool_failure:
            original = tools.registry.get("kb.read")
            def execute(payload):
                if not self.failure_used:
                    self.failure_used = True
                    raise ToolExecutionError(self.case.tool_failure)
                return original.execute(payload)
            tools.registry._bindings["kb.read"] = replace(original, execute=execute)
        self.flow = ResearchFlow(self.runtime, self.harness, self.rag, tools)

    def rejected_without_dispatch(self, request, preview, token):
        count = len(self.calls)
        try:
            self.flow.execute(self.run_id, request, preview.fingerprint, token)
        except (RuntimeConflictError, RagFingerprintError, PolicyRejectedError):
            rejected = True
        else:
            rejected = False
        return rejected and len(self.calls) == count


def evaluate_research(case, service, workspace):
    fixture = ResearchFixture(case, service, workspace)
    checks, trace, gate_checks, restart_checks = [], {}, [], []
    try:
        with fixture.repository.owner_lease():
            fixture.setup()
            from frag_api.services.rag_service import SOURCE_FILE
            inspected = service.source_service.inspect(SOURCE_FILE)
            request = HarnessRequest(goal=case.query, fileSelections=[{"relativePath": SOURCE_FILE,
                "locatorIds": [item.id for item in inspected.locators], "relevanceReason": "Explicit synthetic trajectory fixture."}])
            preview = fixture.flow.start("harness", request)
            fixture.run_id = preview.run_id
            for index in range(len(case.steps)):
                if index:
                    preview = fixture.flow.preview(fixture.run_id, request)
                if not preview.can_approve or preview.stage != "research":
                    break
                gate_checks.append(fixture.rejected_without_dispatch(request, preview, "not-approved"))
                try:
                    report = fixture.flow.execute(fixture.run_id, request, preview.fingerprint, preview.approval_token)
                except RagOutputError:
                    report = fixture.runtime.repository.get(fixture.run_id)
                    if report.research.status != "error":
                        raise
                gate_checks.append(fixture.rejected_without_dispatch(request, preview, preview.approval_token))
                if case.restart_after_turn == index + 1:
                    before = report.model_dump(by_alias=True)
                    count = len(fixture.calls)
                    fixture.setup()
                    after = fixture.runtime.repository.get(fixture.run_id)
                    restart_checks.append(before == after.model_dump(by_alias=True) and len(fixture.calls) == count)
                    restart_checks.append(fixture.rejected_without_dispatch(request, preview, preview.approval_token))
                if report.research.status != "ready":
                    break
            report = fixture.runtime.repository.get(fixture.run_id)
            checks.extend(score_trajectory(case, report, fixture.calls, gate_checks, restart_checks))
            boundary_request = None
            if report.research.status == "awaiting_context":
                count = len(fixture.calls)
                boundary = fixture.flow.preview(fixture.run_id, request)
                payload = boundary.prepared_call.request_body_input()
                expected = set(report.research.selected_evidence_ids)
                boundary_valid = (boundary.stage == "context" and boundary.can_approve and len(fixture.calls) == count
                    and {row["evidenceId"] for row in payload["evidence"]} == expected
                    and payload["researchMissingInformation"] == report.research.missing_information)
                checks.append(EvalCheck(id="research.context_boundary", stage="trajectory", category="host_enforcement",
                    status="PASS" if boundary_valid else "FAIL",
                    detail="Finish freezes only observed evidence and missing information in a new unexecuted Context approval."))
                boundary_request = boundary.prepared_call.model_dump(by_alias=True)
                report = fixture.runtime.repository.get(fixture.run_id)
            trace = {"researchRequests": [call.model_dump(by_alias=True) for call, _ in fixture.calls],
                     "researchOutputs": [output for _, output in fixture.calls],
                     "researchReport": report.model_dump(by_alias=True)}
            if boundary_request is not None:
                trace["contextBoundaryRequest"] = boundary_request
    except Exception:
        checks.append(EvalCheck(id="research.runner_error", stage="trajectory", category="host_enforcement", status="ERROR",
                               detail="Research fixture execution or scorer failed; no PASS is inferred from an exception."))
    finally:
        if fixture.runtime is not None:
            fixture.runtime.close()
    checks.append(EvalCheck(id="semantic.review", stage="semantic", category="semantic_review", status="UNDETERMINED",
                           detail="Scripted synthetic paths do not establish real-model quality or semantic support."))
    failures = [item for item in checks if item.status == "FAIL"]
    return EvalCaseReport(id=case.id, query=case.query, status=aggregate([item.status for item in checks]),
        hostEnforcementStatus=aggregate([item.status for item in checks if item.category == "host_enforcement"]),
        modelQualityStatus=aggregate([item.status for item in checks if item.category == "model_quality"]),
        earliestObservedDeviation=failures[0].stage if failures else None,
        secondaryObservedFailures=[item.id for item in failures[1:]], checks=checks, trace=trace)
