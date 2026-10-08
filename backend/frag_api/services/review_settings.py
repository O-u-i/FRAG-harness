"""Resolve defaults before preparing a request, never while recovering one."""
from frag_api.errors import RequestContractError, RuntimeConflictError
from frag_api.schemas.agents import AgentPrepare
from frag_api.schemas.review_settings import ApplicationSettings, EvidenceSettings, ConversationSettings
from frag_api.schemas.runtime import RunConfiguration


class ReviewSettings:
    def __init__(self, host, application, project):
        self.host, self.application, self.project = host, application, project

    def view(self, session_id=None):
        application = self.application.get("application", ApplicationSettings().model_dump(by_alias=True))
        default = EvidenceSettings(mode=application["settings"]["mode"]).model_dump(by_alias=True)
        project = self.project.get("project", default)
        conversation = {"revision": 0, "settings": None}
        if session_id:
            self.host.current(session_id)
            conversation = self.project.get(f"conversation:{session_id}", None)
        return {"application": application, "project": project, "conversation": conversation}

    def put_application(self, body):
        return self.application.put("application", body.revision, body.settings.model_dump(by_alias=True))

    def put_project(self, body):
        return self.project.put("project", body.revision, body.settings.model_dump(by_alias=True))

    def put_conversation(self, session_id, body):
        with self.host.lock:
            self.host.check(session_id, body.version, body.turn_id)
            return self.project.put(f"conversation:{session_id}", body.revision,
                                    body.settings.model_dump(by_alias=True) if body.settings else None)

    def prepare(self, session_id, body):
        with self.host.lock:
            saved = self.view(session_id)
            for name in ("application", "project", "conversation"):
                if saved[name]["revision"] != getattr(body, f"{name}_revision"):
                    raise RuntimeConflictError()
            carrier, turn = self.host.check(session_id, body.version, body.turn_id)
            app = ApplicationSettings.model_validate(saved["application"]["settings"])
            configured = body.override or (ConversationSettings.model_validate(saved["conversation"]["settings"])
                                           if saved["conversation"]["settings"] else None)
            evidence = configured.evidence if configured else EvidenceSettings.model_validate(saved["project"]["settings"])
            if not evidence.ready:
                raise RequestContractError([{"path": "evidence", "message": "No project evidence configured. Select sources in Settings or customize this task."}])
            task = body.task or {"templateId": "evidence-review-v1", "checklist": [
                {**item.model_dump(), "status": "pending", "reviewed": False}
                for item in (configured.checklist if configured else app.checklist)]}
            common = {"sessionId": session_id, "parentRunId": turn.run_id, "task": task,
                      "selectedMemory": body.selected_memory}
            kind = "rag" if evidence.mode == "retrieval" else "harness"
            selected = ({**common, "query": turn.text, "topK": configured.top_k if configured else app.top_k,
                         "datasetId": "synthetic-risk-review-v1" if evidence.synthetic else "selected-local-v1",
                         "sourceSelection": evidence.file} if kind == "rag" else
                        {**common, "goal": turn.text, "fileSelections": [evidence.file] if evidence.file else [],
                         "pluginSelection": evidence.plugin})
            value = self.host.prepare(session_id, AgentPrepare(version=carrier.version, turnId=turn.id,
                kind=kind, sourceRequest=selected, research=configured.research if configured else False))
            metadata = {"applicationRevision": body.application_revision, "projectRevision": body.project_revision,
                        "conversationRevision": body.conversation_revision,
                        "origin": "run" if body.override else "conversation" if configured else "defaults"}
            # Outside selection/binding: legacy snapshot digests and recovery remain untouched.
            report = self.host.runtime.repository.update(value["report"].run.id,
                lambda record: setattr(record, "configuration", RunConfiguration.model_validate(metadata)))
            pending = self.host.pending[session_id]
            self.host.pending[session_id] = (*pending[:2], report.run.version, *pending[3:])
            value["report"] = report
            return value
