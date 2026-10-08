"""One approved LangGraph research/formal-stage dispatch at a time; no auto model turn."""
from types import SimpleNamespace
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError
from frag_api.errors import (PolicyRejectedError, RagFingerprintError, RagNotReadyError,
    RagOutcomeUnknownError, RagOutputError, RagProviderError, RequestBudgetError, RuntimeConflictError)
from frag_api.providers.llm import provider_for
from frag_api.providers.prepared import output_model_for, verify_prepared
from frag_api.request_spec import estimated_tokens, fingerprint
from frag_api.schemas.governance import LoopDefinition
from frag_api.schemas.research import ResearchPreview, ResearchState
from frag_api.services.approval import ApprovalRegistry
from frag_api.services.research_checkpoint import checkpoint_research, validate_decision
from frag_api.services.research_requests import configuration_hash, prepare_request, revalidate
from frag_api.services.runtime_policy import RunBudget


class ResearchGraphState(TypedDict, total=False):
    run_id: str
    source: object
    prepared: object
    call_id: str
    fingerprint: str
    token: str
    fresh: object
    service: object
    report: object
    result: object


class ResearchFlow:
    def __init__(self, runtime, harness, rag, tools):
        self.runtime, self.tools = runtime, tools
        self.services = {"harness":harness, "rag":rag}
        self.definition = LoopDefinition(name="research", version="1.0.0", stages=("research", "context", "inference"))
        self.approvals = ApprovalRegistry()
        for service in self.services.values():
            service.research = self
            if not hasattr(service, "research_provider"):
                service.research_provider = provider_for(service.settings.research or service.settings.context)
            service.flow.loops._bindings.pop("research", None)
            service.flow.loops.register(self.definition, self)
        graph = StateGraph(ResearchGraphState)
        nodes = [("revalidate", self._validate), ("authorize", self._authorize),
                 ("model_call", self._model_call), ("checkpoint", self._checkpoint), ("tools", self._tools)]
        for name, function in nodes:
            graph.add_node(name, function)
        graph.add_edge(START, nodes[0][0])
        for current, following in zip(nodes, nodes[1:]):
            graph.add_edge(current[0], following[0])
        graph.add_edge(nodes[-1][0], END)
        self.graph = graph.compile()

    def close(self):
        self.approvals.clear()

    def _dto(self, report, prepared, token):
        context = next((item.prepared_call.fingerprint for item in reversed(report.requests)
                        if item.stage == "context" and item.structural_validation == "PASS"), None)
        return ResearchPreview(runId=report.run.id, sessionId=report.run.session_id, stage=prepared.purpose,
            preparedCall=prepared, fingerprint=prepared.fingerprint, approvalToken=token,
            canApprove=token is not None, turn=max(1, len(report.research.turns)),
            warnings=["Each model request requires a new exact approval.",
                      "Tool observations and valid citations do not establish factual support."],
            contextFingerprint=prepared.fingerprint if prepared.purpose == "context" else context)

    def start(self, kind, source):
        service = self.services[kind]
        if getattr(source, "plugin_selection", None) is not None:
            raise PolicyRejectedError()
        fresh = service.flow.prepare_preview(source)
        if any(item.identity.kind == "fc_record" for item in fresh.source_bindings):
            raise PolicyRejectedError()
        research = ResearchState(configurationHash=configuration_hash(service, fresh, self.tools, self.definition))
        draft = SimpleNamespace(selection=SimpleNamespace(goal=service.flow.goal_for(source),
            task=fresh.task, source_bindings=fresh.source_bindings, candidate_evidence=fresh.candidate_evidence),
            research=research, tool_calls=[], requests=[], reviews=[])
        prepared = prepare_request(service, draft, fresh, self.tools, self.definition, "research")
        RunBudget().reserve(prepared)
        frozen = fresh.model_copy(deep=True, update={"prepared_call":prepared})
        run_id, _, call_id = self.runtime.start(kind, source, frozen, research=research)
        token = None
        if fresh.can_approve:
            token = self.approvals.issue(prepared.fingerprint, (run_id, call_id, prepared))
            self.runtime.remember_approval(token)
        return self._dto(self.runtime.repository.get(run_id), prepared, token)

    def validate_source(self, report, source):
        return revalidate(self.runtime, report, source, self.services[report.run.kind], self.tools, self.definition)

    def _resume_tools(self, run_id, source, expected_version):
        saved = self.runtime.repository.get(run_id)
        if saved.run.version != expected_version:
            raise RuntimeConflictError()
        if not any(turn.status == "tools_pending" for turn in saved.research.turns):
            return False
        def resume(current):
            if current.run.version != expected_version:
                raise RuntimeConflictError()
            if current.run.status == "paused":
                current.run.status = "ready_research"
        self.runtime.repository.update(run_id, resume)
        self._run_tools(run_id, source)
        return True

    def preview(self, run_id, source):
        report = self.runtime.repository.get(run_id)
        fresh = self.validate_source(report, source)
        original_version = report.run.version
        reviews_hash = fingerprint([review.model_dump(by_alias=True) for review in report.reviews])
        resumed_tools = self._resume_tools(run_id, source, original_version)  # Explicit resume only; never from startup.
        report = self.runtime.repository.get(run_id)
        if (fingerprint([review.model_dump(by_alias=True) for review in report.reviews]) != reviews_hash
                or (not resumed_tools and report.run.version != original_version)):
            raise RuntimeConflictError()
        if report.research.status in ("error", "exhausted", "outcome_unknown"):
            raise RuntimeConflictError()
        stage = "inference" if report.context else "context" if report.research.status == "awaiting_context" else "research"
        if stage == "research" and not any(turn.status == "model_pending" for turn in report.research.turns) and len(report.research.turns) >= 3:
            raise RuntimeConflictError()
        prepared = prepare_request(self.services[report.run.kind], report, fresh, self.tools, self.definition, stage)
        try:
            RunBudget(report.run_token_limit, report.consumed_tokens).reserve(prepared)
            call_id = self.runtime.prepare(run_id, prepared, stage, allow_paused=True, expected_version=report.run.version)
        except RequestBudgetError:
            def exhausted(current):
                current.research.status = "exhausted"
                if current.run.status not in ("paused", "rejected"):
                    current.run.status = "error"
            self.runtime.repository.update(run_id, exhausted)
            raise
        token = self.approvals.issue(prepared.fingerprint, (run_id, call_id, prepared))
        self.runtime.remember_approval(token)
        return self._dto(self.runtime.repository.get(run_id), prepared, token)

    def execute(self, run_id, source, approved_fingerprint, token):
        with tracing_context(enabled=False):
            self.graph.invoke({"run_id":run_id, "source":source, "fingerprint":approved_fingerprint, "token":token},
                              config={"callbacks":[]})
        return self.runtime.repository.get(run_id)

    def _validate(self, state):
        report = self.runtime.repository.get(state["run_id"])
        return {"report":report, "service":self.services[report.run.kind],
                "fresh":self.validate_source(report, state["source"])}

    def _authorize(self, state):
        valid, pending = self.approvals.consume_state(state["token"], state["fingerprint"])
        if not valid or pending is None or pending[0] != state["run_id"]:
            raise RagFingerprintError()
        _, call_id, prepared = pending
        current = prepare_request(state["service"], state["report"], state["fresh"], self.tools, self.definition, prepared.purpose)
        if current.fingerprint != prepared.fingerprint:
            raise RagFingerprintError()
        settings = getattr(state["service"].settings, prepared.purpose) or state["service"].settings.context
        if not settings.ready:
            raise RagNotReadyError()
        verify_prepared(prepared, settings)
        output_model_for(prepared)
        self.runtime.claim(state["run_id"], call_id, prepared)
        return {"prepared":prepared, "call_id":call_id}

    def _model_call(self, state):
        provider = getattr(state["service"], f"{state['prepared'].purpose}_provider")
        try:
            result = provider.execute_prepared(state["prepared"])
        except Exception as error:
            unknown = isinstance(error, RagOutcomeUnknownError) or not isinstance(error, (RagOutputError, RagProviderError))
            self.runtime.failure(state["run_id"], state["call_id"],
                "LLM_OUTCOME_UNKNOWN" if unknown else "MODEL_CALL_FAILED", unknown=unknown)
            if unknown:
                raise RagOutcomeUnknownError() from error
            raise
        try:
            raw = output_model_for(state["prepared"]).model_validate(result.output)
            if state["prepared"].purpose == "research":
                # Reject malformed raw args before durable_value can remove forbidden keys.
                validate_decision(self.runtime.repository.get(state["run_id"]), raw, self.runtime.redaction_secrets)
            self.runtime.returned(state["run_id"], state["call_id"], result.output, result.usage,
                                  native_replay=getattr(result, "native_replay", None))
        except (ValueError, ValidationError, RagOutputError) as error:
            self.runtime.failure(state["run_id"], state["call_id"], "INVALID_LLM_OUTPUT")
            raise RagOutputError() from error
        return {"result":result}

    def _checkpoint(self, state):
        report = self.runtime.repository.get(state["run_id"])
        call = next(item for item in report.requests if item.id == state["call_id"])
        try:
            if report.consumed_tokens > report.run_token_limit:
                raise RequestBudgetError()
            output = output_model_for(state["prepared"]).model_validate(call.output)
            if estimated_tokens(output.model_dump(by_alias=True)) > state["prepared"].output_limit:
                raise RagOutputError()
            if state["prepared"].purpose == "research":
                checkpoint_research(self.runtime, state["run_id"], state["call_id"], output)
            else:
                allowed = set(report.research.selected_evidence_ids) if state["prepared"].purpose == "context" else {row.evidence_id for row in report.context.evidence}
                if state["prepared"].purpose == "context":
                    ids = [row.evidence_id for row in output.evidence]
                    valid = len(ids) == len(allowed) and set(ids) == allowed
                else:
                    ids = {key for claim in output.claims for key in claim.evidence_ids}
                    valid = bool(ids) and ids.issubset(allowed)
                if not valid:
                    raise RagOutputError()
                required_missing = set(report.research.missing_information)
                if report.context and state["prepared"].purpose == "inference":
                    required_missing.update(report.context.missing_information)
                if not required_missing.issubset(output.missing_information):
                    raise RagOutputError()
                self.runtime.checkpoint(state["run_id"], state["call_id"], output, stage=state["prepared"].purpose)
        except (ValueError, ValidationError, RagOutputError, RequestBudgetError) as error:
            self.runtime.failure(state["run_id"], state["call_id"],
                "REQUEST_BUDGET_EXCEEDED" if isinstance(error, RequestBudgetError) else "INVALID_LLM_OUTPUT")
            if isinstance(error, RequestBudgetError):
                raise
            raise RagOutputError() from error
        return {}

    def _run_tools(self, run_id, source):
        report = self.runtime.repository.get(run_id)
        turn = next((item for item in report.research.turns if item.status == "tools_pending"), None)
        if turn is None or report.run.status in ("paused", "rejected"):
            return
        for call in turn.decision.tool_calls:
            current = self.runtime.repository.get(run_id)
            if current.run.status in ("paused", "rejected"):
                return
            prior = next((item for item in current.tool_calls if item.call_id == call.call_id), None)
            if prior:
                if prior.status in ("dispatching", "outcome_unknown"):
                    raise RuntimeConflictError()
                continue
            self.tools.execute(run_id, source.model_dump(by_alias=True), call, research=True)
        def done(current):
            saved = next(item for item in current.research.turns if item.attempt_id == turn.attempt_id)
            saved.status = "completed"
            if len(current.research.turns) >= 3:
                current.research.status = "exhausted"
                if current.run.status not in ("paused", "rejected"):
                    current.run.status = "error"
            current.run.active_call_id = None
        self.runtime.repository.update(run_id, done)

    def _tools(self, state):
        if state["prepared"].purpose == "research":
            self._run_tools(state["run_id"], state["source"])
        return {}
