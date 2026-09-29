"""Embedded LangGraph for the two separately approved model stages."""
from __future__ import annotations

import json
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from frag_api.errors import RagFingerprintError, RagNotReadyError, RagOutputError
from frag_api.providers.llm import LlmProvider, LlmSettings, inference_input
from frag_api.schemas.common import StageResult
from frag_api.schemas.rag import (
    InferencePreview, RagContextCompression, RagGroundedAnswer,
)
from frag_api.services.approval import ApprovalRegistry, PendingInferenceRegistry
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT, estimated_tokens, fingerprint,
)


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
        if state["issue_approval"]:
            state["preview"].approval_token = self.approvals.issue(state["preview"].context_fingerprint)
        return {"preview": state["preview"]}

    def _authorize(self, state: FlowState) -> FlowState:
        preview = state["preview"]
        request = state["request"]
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        if not preview.candidate_evidence:
            raise RagOutputError()
        if not self.settings.context.ready or not self.settings.inference.ready:
            raise RagNotReadyError()
        if not self.approvals.consume(request.approval_token, preview.context_fingerprint):
            raise RagFingerprintError()
        preview.approval_token = request.approval_token
        return {"preview": preview}

    def _context_call(self, state: FlowState) -> FlowState:
        call = self.context_provider().generate_rag_context(state["preview"].candidate_evidence, CONTEXT_OUTPUT_LIMIT)
        return {"compressed": call.output,
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=call.usage)}

    @staticmethod
    def _context_check(state: FlowState) -> FlowState:
        compressed = state["compressed"]
        if not isinstance(compressed, RagContextCompression):
            raise RagOutputError()
        allowed = {item.chunk_id for item in state["preview"].candidate_evidence}
        returned = {item.chunk_id for item in compressed.evidence}
        if returned != allowed or estimated_tokens(compressed.model_dump(by_alias=True)) > CONTEXT_OUTPUT_LIMIT:
            raise RagOutputError()
        return {}

    def _inference_preview(self, state: FlowState) -> FlowState:
        instructions, payload = inference_input(state["compressed"], state["goal"])
        outbound = json.dumps(payload, ensure_ascii=False)
        digest = fingerprint({
            "instructions": instructions, "input": outbound,
            "provider": self.settings.inference.provider, "model": self.settings.inference.model,
            "maxOutputTokens": INFERENCE_OUTPUT_LIMIT,
            "contextFingerprint": state["preview"].context_fingerprint,
        })
        pending = (state["source_request"], state["preview"], state["compressed"],
                   state["context_stage"].usage)
        token = self.pending_inference.issue(digest, pending)
        return {"inference_preview": InferencePreview(
            provider=self.settings.inference.provider, model=self.settings.inference.model,
            instructions=instructions, input=outbound, maxOutputTokens=INFERENCE_OUTPUT_LIMIT,
            inferenceFingerprint=digest, approvalToken=token,
        )}

    def _consume(self, state: FlowState) -> FlowState:
        request = state["request"]
        pending = self.pending_inference.consume(request.approval_token, request.inference_fingerprint)
        if pending is None:
            raise RagFingerprintError()
        source_request, preview, compressed, usage = pending
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        return {"source_request": source_request, "preview": preview, "compressed": compressed,
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=usage),
                "goal": self.goal_for(source_request)}

    def _revalidate(self, state: FlowState) -> FlowState:
        current = self.prepare_preview(state["source_request"])
        if current.context_fingerprint != state["preview"].context_fingerprint:
            raise RagFingerprintError()
        return {}

    def _inference_call(self, state: FlowState) -> FlowState:
        call = self.inference_provider().generate_rag_answer(
            state["compressed"], state["goal"], INFERENCE_OUTPUT_LIMIT,
        )
        return {"answer": call.output,
                "inference_stage": StageResult(provider=self.settings.inference.provider,
                                               model=self.settings.inference.model, usage=call.usage)}

    @staticmethod
    def _citation_check(state: FlowState) -> FlowState:
        answer = state["answer"]
        if not isinstance(answer, RagGroundedAnswer):
            raise RagOutputError()
        allowed = {item.chunk_id for item in state["compressed"].evidence}
        cited = {chunk_id for claim in answer.claims for chunk_id in claim.chunk_ids}
        if not cited or not cited.issubset(allowed):
            raise RagOutputError()
        return {}
