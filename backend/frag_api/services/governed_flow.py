"""Embedded LangGraph for the two separately approved model stages."""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from frag_api.errors import (RagFingerprintError, RagNotReadyError, RagOutputError,
                             RagProviderError, RagOutcomeUnknownError, RuntimeConflictError)
from frag_api.providers.llm import LlmCallResult, LlmProvider, LlmSettings, inference_input
from frag_api.providers.prepared import prepare_call, verify_prepared
from frag_api.schemas.common import StageResult
from frag_api.schemas.governance import LoopDefinition, PreparedCall
from frag_api.schemas.rag import (
    InferencePreview, RagContextCompression, RagGroundedAnswer,
)
from frag_api.services.approval import ApprovalRegistry, PendingInferenceRegistry
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT, estimated_tokens,
)
from frag_api.services.runtime_policy import HostPolicy, RunBudget, configured_secrets, redact_value
from frag_api.services.runtime_registry import LoopRegistry
from frag_api.request_spec import fingerprint


class FlowState(TypedDict, total=False):
    source_request: Any
    request: Any
    preview: Any
    issue_approval: bool
    compressed: RagContextCompression
    context_stage: StageResult
    inference_preview: InferencePreview
    answer: RagGroundedAnswer
    inference_stage: StageResult
    goal: str
    inference_prepared: PreparedCall
    run_budget: RunBudget
    runtime_call_id: str | None
    resuming: bool


class GovernedFlow:
    def __init__(
        self,
        *,
        prepare_preview: Callable[[Any], Any],
        goal_for: Callable[[Any], str],
        settings: LlmSettings,
        context_provider: Callable[[], LlmProvider],
        inference_provider: Callable[[], LlmProvider],
        approvals: ApprovalRegistry,
        pending_inference: PendingInferenceRegistry,
    ):
        self.prepare_preview = prepare_preview
        self.goal_for = goal_for
        self.settings = settings
        self.context_provider = context_provider
        self.inference_provider = inference_provider
        self.approvals = approvals
        self.pending_inference = pending_inference
        self.runtime = None
        self.kind = "harness"
        self.preview_graph = self._compile([("prepare", self._prepare), ("issue", self._issue)])
        self.context_graph = self._compile([
            ("prepare", self._prepare), ("authorize", self._authorize),
            ("context_call", self._context_call), ("context_check", self._context_check),
            ("inference_preview", self._inference_preview),
        ])
        self.inference_graph = self._compile([
            ("consume", self._consume), ("revalidate", self._revalidate),
            ("inference_call", self._inference_call), ("citation_check", self._citation_check),
        ])
        self.loops = LoopRegistry()
        self.loops.register(LoopDefinition(name="fixed", version="1.0.0", stages=("context", "inference")), self)

    @staticmethod
    def _compile(nodes: list[tuple[str, Callable[[FlowState], FlowState]]]):
        graph = StateGraph(FlowState)
        for name, node in nodes:
            graph.add_node(name, node)
        graph.add_edge(START, nodes[0][0])
        for current, following in zip(nodes, nodes[1:]):
            graph.add_edge(current[0], following[0])
        graph.add_edge(nodes[-1][0], END)
        return graph.compile()  # No checkpointer or persistent graph state.

    @staticmethod
    def _invoke(graph: Any, state: FlowState) -> FlowState:
        with tracing_context(enabled=False):
            return graph.invoke(state, config={"callbacks": []})

    def preview(self, source_request: Any, *, issue_approval: bool = True) -> Any:
        state = self._invoke(self.preview_graph, {
            "source_request": source_request, "issue_approval": issue_approval,
        })
        return state["preview"]

    def run_context(self, source_request: Any, request: Any) -> FlowState:
        return self._invoke(self.context_graph, {"source_request": source_request, "request": request})

    def run_inference(self, request: Any) -> FlowState:
        return self._invoke(self.inference_graph, {"request": request})

    def _prepare(self, state: FlowState) -> FlowState:
        return {"preview": self.prepare_preview(state["source_request"]),
                "goal": self.goal_for(state["source_request"])}

    def _issue(self, state: FlowState) -> FlowState:
        call_id = None
        if state["issue_approval"] and self.runtime:
            run_id, session_id, call_id = self.runtime.start(self.kind, state["source_request"], state["preview"])
            state["preview"].run_id, state["preview"].session_id = run_id, session_id
        if state["issue_approval"] and state["preview"].can_approve:
            # The caller receives a copy; only this server-owned snapshot may execute.
            pending = (state["source_request"].model_copy(deep=True), state["preview"].model_copy(deep=True), call_id)
            state["preview"].approval_token = self.approvals.issue(state["preview"].context_fingerprint, pending)
            if self.runtime:
                self.runtime.remember_approval(state["preview"].approval_token)
        return {"preview": state["preview"]}

    def _authorize(self, state: FlowState) -> FlowState:
        request = state["request"]
        valid, pending = self.approvals.consume_state(request.approval_token, request.context_fingerprint)
        if not valid or pending is None:
            raise RagFingerprintError()
        source_request, preview, call_id = pending
        if request.context_fingerprint != state["preview"].context_fingerprint:
            raise RagFingerprintError()
        HostPolicy.require_task(preview.task)
        if not preview.candidate_evidence:
            raise RagOutputError()
        if not self.settings.context.ready or not self.settings.inference.ready:
            raise RagNotReadyError()
        verify_prepared(preview.prepared_call, self.settings.context)
        consumed = self.runtime.repository.get(preview.run_id).consumed_tokens if self.runtime else 0
        budget = RunBudget(limit=preview.prepared_call.run_token_limit, consumed=consumed)
        budget.reserve(preview.prepared_call)
        preview.approval_token = request.approval_token
        return {"source_request": source_request, "preview": preview, "run_budget": budget,
                "goal": self.goal_for(source_request), "runtime_call_id": call_id}

    def _execute(self, state, prepared, provider):
        run_id, call_id = state["preview"].run_id, state.get("runtime_call_id")
        if self.runtime:
            self.runtime.claim(run_id, call_id, prepared)
        try:
            result = provider.execute_prepared(prepared)
        except Exception as error:
            if self.runtime:
                unknown = isinstance(error, RagOutcomeUnknownError) or not isinstance(error, (RagOutputError, RagProviderError))
                code = "LLM_OUTCOME_UNKNOWN" if unknown else "MODEL_CALL_FAILED"
                self.runtime.failure(run_id, call_id, code, unknown=unknown)
                if unknown:
                    raise RagOutcomeUnknownError() from error
            raise
        if isinstance(result.output, (RagContextCompression, RagGroundedAnswer)):
            secrets = self.runtime.redaction_secrets if self.runtime else configured_secrets(self.settings)
            output = type(result.output).model_validate(redact_value(result.output.model_dump(by_alias=True), secrets))
            result = LlmCallResult(output, result.usage)
        if self.runtime:
            self.runtime.returned(run_id, call_id, result.output, result.usage)
        return result

    def _charge(self, state, prepared, usage):
        try:
            return state["run_budget"].charge(prepared, usage)
        except Exception:
            if self.runtime:
                self.runtime.failure(state["preview"].run_id, state["runtime_call_id"], "REQUEST_BUDGET_EXCEEDED")
            raise

    def _context_call(self, state: FlowState) -> FlowState:
        prepared = state["preview"].prepared_call
        call = self._execute(state, prepared, self.context_provider())
        return {"compressed": call.output, "run_budget": self._charge(state, prepared, call.usage),
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=call.usage)}

    def _context_check(self, state: FlowState) -> FlowState:
        compressed = state["compressed"]
        if not isinstance(compressed, RagContextCompression):
            if self.runtime:
                self.runtime.failure(state["preview"].run_id, state["runtime_call_id"], "INVALID_LLM_OUTPUT")
            raise RagOutputError()
        allowed = {item.evidence_id for item in state["preview"].candidate_evidence}
        returned = {item.evidence_id for item in compressed.evidence}
        if (returned != allowed or len(returned) != len(compressed.evidence)
                or estimated_tokens(compressed.model_dump(by_alias=True)) > CONTEXT_OUTPUT_LIMIT):
            if self.runtime:
                self.runtime.failure(state["preview"].run_id, state["runtime_call_id"], "INVALID_LLM_OUTPUT")
            raise RagOutputError()
        if self.runtime:
            self.runtime.checkpoint(state["preview"].run_id, state["runtime_call_id"], compressed, stage="context")
        return {}

    def _prepare_inference(self, state: FlowState) -> PreparedCall:
        instructions, payload = inference_input(state["compressed"], state["goal"])
        payload["task"] = state["preview"].task.model_dump(by_alias=True)
        return prepare_call(
            settings=self.settings.inference, purpose="inference", instructions=instructions,
            payload=redact_value(payload, self.runtime.redaction_secrets if self.runtime else configured_secrets(self.settings)), output_model=RagGroundedAnswer,
            max_output_tokens=INFERENCE_OUTPUT_LIMIT,
            binding={**state["preview"].prepared_call.request_binding(),
                     "contextFingerprint": state["preview"].context_fingerprint},
        )
    def _inference_preview(self, state: FlowState) -> FlowState:
        prepared = self._prepare_inference(state)
        state["run_budget"].reserve(prepared)
        call_id = self.runtime.prepare(state["preview"].run_id, prepared, "inference", allow_paused=state.get("resuming", False)) if self.runtime else None
        pending = (state["source_request"].model_copy(deep=True), state["preview"].model_copy(deep=True),
                   state["compressed"].model_copy(deep=True), state["context_stage"].usage.model_copy(deep=True),
                   prepared, state["run_budget"], call_id)
        token = self.pending_inference.issue(prepared.fingerprint, pending)
        if self.runtime:
            self.runtime.remember_approval(token)
        body = prepared.request_body()
        return {"inference_preview": InferencePreview(
            provider=self.settings.inference.provider, model=self.settings.inference.model,
            instructions=body["instructions"], input=body["input"], maxOutputTokens=INFERENCE_OUTPUT_LIMIT,
            inferenceFingerprint=prepared.fingerprint, approvalToken=token, preparedCall=prepared,
        )}

    @staticmethod
    def _same_recovery_spec(old, new):
        old_binding, new_binding = old.request_binding(), new.request_binding()
        for key in ("selectionHash", "contextFingerprint"):
            old_binding.pop(key, None)
            new_binding.pop(key, None)
        return (old.model_dump(by_alias=True, exclude={"fingerprint", "binding"})
                == new.model_dump(by_alias=True, exclude={"fingerprint", "binding"})
                and old_binding == new_binding)

    def _consume(self, state: FlowState) -> FlowState:
        request = state["request"]
        pending = self.pending_inference.consume(request.approval_token, request.inference_fingerprint)
        if pending is None:
            raise RagFingerprintError()
        source_request, preview, compressed, usage, prepared, budget, call_id = pending
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        return {"source_request": source_request, "preview": preview, "compressed": compressed,
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=usage),
                "goal": self.goal_for(source_request), "inference_prepared": prepared, "run_budget": budget,
                "runtime_call_id": call_id}

    def _revalidate(self, state: FlowState) -> FlowState:
        current = self.prepare_preview(state["source_request"])
        if current.context_fingerprint != state["preview"].context_fingerprint:
            raise RagFingerprintError()
        HostPolicy.require_task(current.task)
        verify_prepared(state["inference_prepared"], self.settings.inference)
        if self._prepare_inference(state).fingerprint != state["inference_prepared"].fingerprint:
            raise RagFingerprintError()
        state["run_budget"].reserve(state["inference_prepared"])
        return {}

    def _inference_call(self, state: FlowState) -> FlowState:
        prepared = state["inference_prepared"]
        call = self._execute(state, prepared, self.inference_provider())
        return {"answer": call.output, "run_budget": self._charge(state, prepared, call.usage),
                "inference_stage": StageResult(provider=self.settings.inference.provider,
                                               model=self.settings.inference.model, usage=call.usage)}

    def _citation_check(self, state: FlowState) -> FlowState:
        answer = state["answer"]
        if not isinstance(answer, RagGroundedAnswer):
            if self.runtime:
                self.runtime.failure(state["preview"].run_id, state["runtime_call_id"], "INVALID_LLM_OUTPUT")
            raise RagOutputError()
        allowed = {item.evidence_id for item in state["compressed"].evidence}
        cited = {evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids}
        if (not cited or not cited.issubset(allowed)
                or estimated_tokens(answer.model_dump(by_alias=True)) > INFERENCE_OUTPUT_LIMIT):
            if self.runtime:
                self.runtime.failure(state["preview"].run_id, state["runtime_call_id"], "INVALID_LLM_OUTPUT")
            raise RagOutputError()
        if self.runtime:
            self.runtime.checkpoint(state["preview"].run_id, state["runtime_call_id"], answer, stage="inference")
        return {}

    def resume_preview(self, run_id, source_request):
        """Explicit reselection restores a checkpoint, never an old token or an external call."""
        if self.runtime is None:
            raise RuntimeConflictError()
        saved = self.runtime.repository.get(run_id)
        if saved.snapshot_digest and saved.snapshot_digest != fingerprint(saved.selection.model_dump(by_alias=True)):
            raise RagFingerprintError()
        if (saved.run.kind != self.kind or saved.model_output is not None
                or saved.run.status in ("accepted", "rejected", "outcome_unknown")
                or any(c.status == "dispatching" or (c.status == "completed" and c.structural_validation == "UNDETERMINED") for c in saved.requests)):
            raise RuntimeConflictError()
        current = self.prepare_preview(source_request)
        old = saved.requests[0].prepared_call
        new = current.prepared_call
        if (not self._same_recovery_spec(old, new)
                or current.candidate_evidence != saved.selection.candidate_evidence
                or not current.can_approve):
            raise RagFingerprintError()
        current.run_id, current.session_id = saved.run.id, saved.run.session_id
        if saved.context is None:
            call_id = self.runtime.prepare(run_id, new, "context", allow_paused=True)
            current.approval_token = self.approvals.issue(new.fingerprint, (source_request.model_copy(deep=True), current.model_copy(deep=True), call_id))
            self.runtime.remember_approval(current.approval_token)
            return "context", current, current.context_fingerprint
        context_call = next(c for c in saved.requests if c.stage == "context" and c.structural_validation == "PASS")
        state = {"source_request":source_request, "preview":current, "compressed":saved.context,
                 "goal":self.goal_for(source_request), "run_budget":RunBudget(saved.run_token_limit, saved.consumed_tokens),
                 "resuming":True,
                 "context_stage":StageResult(provider=context_call.prepared_call.provider, model=context_call.prepared_call.model, usage=context_call.usage)}
        previous_inference = next((c for c in reversed(saved.requests) if c.stage == "inference"), None)
        if previous_inference and not self._same_recovery_spec(previous_inference.prepared_call, self._prepare_inference(state)):
            raise RagFingerprintError()
        preview = self._inference_preview(state)["inference_preview"]
        return "inference", preview, current.context_fingerprint
