"""Host CLI requests are API operations; model execution stays interactive."""
from typing import Any, Literal

from pydantic import Field, model_validator

from frag_api.schemas.common import ApiModel
from frag_api.schemas.context_source import LocalFileInspectRequest
from frag_api.schemas.harness import HarnessRequest
from frag_api.schemas.rag import RagQueryRequest
from frag_api.schemas.runtime import ReviewRequest, RevisionRequest, SessionCreate
from frag_api.schemas.tools import ToolExecutionRequest

HostCommand = Literal[
    "health", "capabilities", "sources", "source-inspect", "sessions", "session-create",
    "runs", "report", "preview", "recovery-preview", "reopen", "review", "revision", "tool-execute", "research-preview",
]
EMPTY_COMMANDS = {"health", "capabilities", "sources", "sessions", "runs", "report"}
RUN_COMMANDS = {"report", "recovery-preview", "reopen", "review", "revision", "tool-execute"}


def source_payload(payload: dict[str, Any], kind: str | None = None) -> dict:
    model = HarnessRequest if (kind == "harness" or (kind is None and "goal" in payload)) else RagQueryRequest
    return model.model_validate(payload).model_dump(by_alias=True, exclude_none=True)


class HostCLIRequest(ApiModel):
    command: HostCommand
    kind: Literal["harness", "rag"] | None = None
    run_id: str | None = Field(default=None, alias="runId", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    session_id: str | None = Field(default=None, alias="sessionId", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    format: Literal["json", "markdown"] = "json"
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def operation_contract(self):
        if self.command in RUN_COMMANDS and self.run_id is None:
            raise ValueError("This operation requires a Run ID.")
        if self.command not in RUN_COMMANDS | {"research-preview"} and self.run_id is not None:
            raise ValueError("This operation has no Run ID.")
        if self.command != "runs" and self.session_id is not None:
            raise ValueError("Only Runs accepts a Session filter.")
        if self.command != "report" and self.format != "json":
            raise ValueError("Only reports support Markdown.")
        if self.command not in {"preview", "recovery-preview", "reopen", "tool-execute", "research-preview"} and self.kind is not None:
            raise ValueError("This operation does not take a source kind.")
        if self.command in EMPTY_COMMANDS and self.payload:
            raise ValueError("This operation has no input body.")
        models = {"session-create": SessionCreate, "source-inspect": LocalFileInspectRequest,
                  "review": ReviewRequest, "revision": RevisionRequest}
        if self.command in models:
            self.payload = models[self.command].model_validate(self.payload).model_dump(by_alias=True)
        elif self.command in {"preview", "research-preview"}:
            if self.kind is None:
                raise ValueError("Preview requires a source kind.")
            self.payload = source_payload(self.payload, self.kind)
        elif self.command in {"recovery-preview", "reopen", "tool-execute"}:
            expected = {"sourceRequest", "call"} if self.command == "tool-execute" else {"sourceRequest"}
            if set(self.payload) != expected or not isinstance(self.payload.get("sourceRequest"), dict):
                raise ValueError("Provide an explicit sourceRequest and the operation's declared fields.")
            self.payload["sourceRequest"] = source_payload(self.payload["sourceRequest"], self.kind)
            if self.command == "tool-execute":
                self.payload = ToolExecutionRequest.model_validate(self.payload).model_dump(by_alias=True)
        return self


class HostCLIResponse(ApiModel):
    command: HostCommand
    result: Any
