"""Translate explicit review actions into existing governed flows, never Send approval."""
from threading import RLock
from contextlib import contextmanager
from frag_api.providers.llm import LlmStageSettings, LlmSettings, provider_for
from frag_api.errors import RagNotReadyError
from frag_api.errors import RuntimeConflictError, RequestContractError
from frag_api.schemas.agents import AgentPrepare, AgentExecute
from frag_api.schemas.harness import HarnessRequest, HarnessRunRequest
from frag_api.schemas.rag import RagQueryRequest, RagRunRequest, InferenceRunRequest
from frag_api.schemas.runtime import RecoveryPreview, ReviewRequest


class AgentReview:
    def __init__(self, app):
        self.app = app
        self.runtime = app.state.runtime
        # ponytail: serialize this local carrier's mutations; per-session locks if needed.
        self.lock = RLock()
        self.pending = {}  # Process-only tokens: reconnect never recreates approval.

    @contextmanager
    def model_route(self, session_id):
        if not self.bridge:
            yield
            return
        carrier = self.current(session_id)
        if not carrier.turns and carrier.model_id is None:
            yield  # An unbound provisional session is readable; mutations still require a saved turn.
            return
        model_id = carrier.turns[-1].model_id if carrier.turns else carrier.model_id
        model = self.bridge.describe(model_id)
        if model is None:
            raise RagNotReadyError()
        stage = LlmStageSettings("vscode", model.id, self.bridge.address, self.bridge.key, 120,
            configuration_revision=model.revision, reasoning_effort=model.effort,
            max_input_tokens=model.max_input_tokens, model_name=model.name, model_vendor=model.vendor)
        settings = LlmSettings(stage, stage, stage)
        saved = []
        # ponytail: one project Host serializes model stages; generic model-dispatch HTTP routes are disabled.
        for service in (self.app.state.harness_service, self.app.state.rag_service):
            saved.append((service, service.settings, service.flow.settings, service.context_provider, service.inference_provider, service.research_provider))
            service.settings = service.flow.settings = settings
            service.context_provider = service.inference_provider = service.research_provider = provider_for(stage)
        try:
            yield
        finally:
            for service, settings, flow_settings, context, inference, research in saved:
                service.settings, service.flow.settings = settings, flow_settings
                service.context_provider, service.inference_provider, service.research_provider = context, inference, research

    def review_view(self, carrier, report, preview):
        return {"session": carrier, "report": report, "preview": preview,
                "project": {"name": self.project_name, "uri": self.workspace},
                "config": self.app.state.harness_service.config()}

    def current(self, session_id):
        return self.runtime.repository.agent_session(session_id)

    def check(self, session_id, version, turn_id):
        carrier = self.current(session_id)
        if carrier.version != version or not carrier.turns or carrier.turns[-1].id != turn_id:
            raise RuntimeConflictError()
        return carrier, carrier.turns[-1]

    def prepare(self, session_id, request: AgentPrepare):
        with self.lock, self.model_route(session_id):
            carrier, turn = self.check(session_id, request.version, request.turn_id)
            if turn.state != "running":
                raise RuntimeConflictError()
            model = HarnessRequest if request.kind == "harness" else RagQueryRequest
            selected = model.model_validate(request.source_request)
            goal = selected.goal if request.kind == "harness" else selected.query
            if (goal != turn.text or selected.session_id != session_id
                    or selected.parent_run_id != turn.run_id):
                raise RequestContractError([{"path": "sourceRequest", "message": "Bind the current native task, session and parent run."}])
            service = self.app.state.harness_service if request.kind == "harness" else self.app.state.rag_service
            self.pending.pop(session_id, None)
            if request.research:
                value = self.app.state.research.start(request.kind, selected)
                preview = RecoveryPreview(runId=value.run_id, kind=request.kind, stage=value.stage,
                    contextFingerprint=value.context_fingerprint or value.fingerprint, preview=value.model_dump(by_alias=True))
            else:
                value = service.preview(selected)
                preview = RecoveryPreview(runId=value.run_id, kind=request.kind, stage="context",
                    contextFingerprint=value.context_fingerprint, preview=value.model_dump(by_alias=True))
            def bind(value):
                value.turns[-1].run_id = preview.run_id
            carrier = self.runtime.repository.update_agent_session(session_id, bind)
            report = self.runtime.repository.get(preview.run_id)
            self.pending[session_id] = (carrier.version, turn.id, report.run.version, selected, preview)
            return self.review_view(carrier, report, preview)

    def recover(self, session_id, version, turn_id):
        with self.lock, self.model_route(session_id):
            carrier, turn = self.check(session_id, version, turn_id)
            if not turn.run_id or turn.state != "running":
                raise RuntimeConflictError()
            report = self.runtime.repository.get(turn.run_id)
            model = HarnessRequest if report.run.kind == "harness" else RagQueryRequest
            selected = model.model_validate(report.selection.input)
            service = self.app.state.harness_service if report.run.kind == "harness" else self.app.state.rag_service
            if report.research:
                value = self.app.state.research.preview(turn.run_id, selected)
                preview = RecoveryPreview(runId=turn.run_id, kind=report.run.kind, stage=value.stage,
                    contextFingerprint=value.context_fingerprint or value.fingerprint, preview=value.model_dump(by_alias=True))
            else:
                stage, value, fingerprint = service.flow.resume_preview(turn.run_id, selected)
                preview = RecoveryPreview(runId=turn.run_id, kind=report.run.kind, stage=stage,
                    contextFingerprint=fingerprint, preview=value.model_dump(by_alias=True))
            report = self.runtime.repository.get(turn.run_id)
            self.pending[session_id] = (carrier.version, turn.id, report.run.version, selected, preview)
            return self.review_view(carrier, report, preview)

    def execute(self, session_id, request: AgentExecute):
        with self.lock, self.model_route(session_id):
            carrier, turn = self.check(session_id, request.version, request.turn_id)
            pending = self.pending.get(session_id)
            if not pending or turn.state != "running" or turn.run_id != request.run_id:
                raise RuntimeConflictError()
            version, turn_id, run_version, selected, preview = pending
            report = self.runtime.repository.get(turn.run_id)
            value = preview.preview
            fingerprint = value.get("fingerprint") or value.get("inferenceFingerprint") or value.get("contextFingerprint")
            if (version != request.version or turn_id != request.turn_id
                    or run_version != request.run_version or report.run.version != run_version
                    or value.get("approvalToken") != request.approval_token or fingerprint != request.fingerprint):
                raise RuntimeConflictError()
            self.pending.pop(session_id)  # Consume locally before dispatch, including failure.
            service = self.app.state.harness_service if report.run.kind == "harness" else self.app.state.rag_service
            if report.research:
                self.app.state.research.execute(turn.run_id, selected, value["fingerprint"], request.approval_token)
            elif preview.stage == "context":
                model = HarnessRunRequest if report.run.kind == "harness" else RagRunRequest
                service.run(model.model_validate({**selected.model_dump(by_alias=True), "approved": True,
                    "contextFingerprint": fingerprint, "approvalToken": request.approval_token}))
            else:
                service.run_inference(InferenceRunRequest(contextFingerprint=preview.context_fingerprint,
                    inferenceFingerprint=fingerprint, approvalToken=request.approval_token, approved=True))
            # Expose a fresh approval for a following stage only on explicit recovery.
            return self.review_view(self.current(session_id), self.runtime.repository.get(turn.run_id), None)

    def cancel(self, session_id, turn_id):
        with self.lock:
            carrier = self.current(session_id)
            if not carrier.turns or carrier.turns[-1].id != turn_id:
                raise RuntimeConflictError()
            if carrier.turns[-1].state == "cancelled":
                return carrier
            if carrier.turns[-1].state != "running":
                raise RuntimeConflictError()
            self.pending.pop(session_id, None)
            turn = carrier.turns[-1]
            if turn.run_id:
                report = self.runtime.repository.get(turn.run_id)
                self.runtime.review(turn.run_id, ReviewRequest(decision="paused", checklist=report.selection.task,
                    note="Paused from the native conversation."))
            def change(value):
                value.turns[-1].state = "cancelled"
            return self.runtime.repository.update_agent_session(session_id, change)
