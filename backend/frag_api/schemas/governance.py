"""Versioned host contracts. Registration and source text never grant authority."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from frag_api.schemas.common import ApiModel, ProviderKind

HOST_VERSION = "1.10.2"
POLICY_VERSION = "selected-read-v1"
REDACTION_VERSION = "outbound-v1"
TASK_TEMPLATE_VERSION = "evidence-review-v1"


class FrozenModel(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class QualityFact(FrozenModel):
    status: Literal["known", "unknown"] = "unknown"
    detail: str | None = None

    @model_validator(mode="after")
    def explicit_unknown(self):
        if (self.status == "known") != bool(self.detail):
            raise ValueError("Known metadata requires detail; unknown metadata has no asserted detail.")
        return self


class SourceAssessment(FrozenModel):
    authority: QualityFact = Field(default_factory=QualityFact)
    freshness: QualityFact = Field(default_factory=QualityFact)
    relevance: QualityFact = Field(default_factory=QualityFact)
    provenance: QualityFact = Field(default_factory=QualityFact)
    permission: Literal["selected_read_only"] = "selected_read_only"


class SourceIdentity(FrozenModel):
    kind: Literal["local_file", "synthetic", "fc_record", "plugin_record"]
    namespace: str = Field(min_length=1)
    resource_id: str = Field(alias="resourceId", min_length=1)
    workspace_id: str | None = Field(default=None, alias="workspaceId")

    @model_validator(mode="after")
    def workspace_scope(self):
        if (self.kind in {"fc_record", "plugin_record"}) != bool(self.workspace_id):
            raise ValueError("Plugin records require a source scope; other source kinds have none.")
        return self


class SourceBinding(FrozenModel):
    identity: SourceIdentity
    revision: str = Field(min_length=1)
    parser_version: str = Field(alias="parserVersion", min_length=1)
    locator_ids: tuple[str, ...] = Field(alias="locatorIds", min_length=1)
    evidence_ids: tuple[str, ...] = Field(alias="evidenceIds", min_length=1)
    assessment: SourceAssessment = Field(default_factory=SourceAssessment)

    @model_validator(mode="after")
    def unique_scope(self):
        for values in (self.locator_ids, self.evidence_ids):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError("Selected scope identifiers must be nonempty and unique.")
        return self


class ChecklistItem(FrozenModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=500)
    blocking: bool = Field(default=False, strict=True)
    status: Literal["pending", "met", "missing", "unknown"] = "pending"
    reviewed: bool = Field(default=False, strict=True)


class TaskContract(FrozenModel):
    template_id: Literal["evidence-review-v1"] = Field(default=TASK_TEMPLATE_VERSION, alias="templateId")
    checklist: tuple[ChecklistItem, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.id for item in self.checklist}) != len(self.checklist):
            raise ValueError("Checklist identifiers must be unique.")
        return self

    @property
    def blocking_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.checklist
                     if item.blocking and (not item.reviewed or item.status != "met"))


class LoopLimits(FrozenModel):
    model_turns: int = Field(default=3, alias="modelTurns", ge=1, le=3)
    tool_calls: int = Field(default=6, alias="toolCalls", ge=1, le=6)
    tool_timeout_seconds: int = Field(default=10, alias="toolTimeoutSeconds", ge=1, le=10)
    tool_result_bytes: int = Field(default=16 * 1024, alias="toolResultBytes", ge=1, le=16 * 1024)
    loop_output_tokens: int = Field(default=800, alias="loopOutputTokens", ge=1, le=800)
    run_token_limit: int = Field(default=30_000, alias="runTokenLimit", gt=0, le=30_000)
    serial_tools: Literal[True] = Field(default=True, alias="serialTools")


class PreparedCall(FrozenModel):
    """Immutable JSON strings prevent mutation of nested request or binding objects."""
    schema_version: Literal[1, 2] = Field(default=1, alias="schemaVersion")
    purpose: Literal["context", "inference", "research"]
    provider: ProviderKind
    model: str
    endpoint: str
    # Legacy transport is readable history only; no provider can execute it.
    transport: Literal["fake", "responses-v1", "pi-responses-v1", "vscode-lm-v1"]
    body: str
    binding: str
    timeout_seconds: float = Field(alias="timeoutSeconds", gt=0, le=120)
    max_retries: Literal[0] = Field(default=0, alias="maxRetries")
    estimated_input_tokens: int = Field(alias="estimatedInputTokens", ge=1)
    input_budget: int = Field(default=6000, alias="inputBudget", gt=0)
    reserved_percent: int = Field(default=25, alias="reservedPercent", ge=0, le=100)
    run_token_limit: int = Field(default=30_000, alias="runTokenLimit", gt=0)
    fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def json_objects(self):
        if not isinstance(json.loads(self.body), dict) or not isinstance(json.loads(self.binding), dict):
            raise ValueError("Prepared body and binding must be JSON objects.")
        return self

    def request_body(self) -> dict:
        return json.loads(self.body)

    def request_body_input(self) -> dict:
        body = self.request_body()
        value = body["messages"][1]["content"] if self.transport == "vscode-lm-v1" else body["input"]
        if isinstance(value, list):
            value = value[0]["content"][0]["text"]
        return json.loads(value)

    @property
    def output_limit(self) -> int:
        body = self.request_body()
        return body["options"]["modelOptions"]["max_tokens"] if self.transport == "vscode-lm-v1" else body["max_output_tokens"]

    def preview_text(self) -> tuple[str, str]:
        body = self.request_body()
        if self.transport == "vscode-lm-v1":
            return body["messages"][0]["content"], body["messages"][1]["content"]
        return body["instructions"], body["input"] if isinstance(body["input"], str) else json.dumps(body["input"], ensure_ascii=False)

    def request_binding(self) -> dict:
        return json.loads(self.binding)


class ToolDefinition(FrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    input_schema: str = Field(alias="inputSchema")
    output_schema: str = Field(alias="outputSchema")
    read_only: Literal[True] = Field(default=True, alias="readOnly")
    source_kinds: tuple[Literal["local_file", "synthetic"], ...] = Field(alias="sourceKinds", min_length=1)
    carrier: Literal["native", "cli"]
    carrier_id: str = Field(alias="carrierId", min_length=1)
    timeout_seconds: int = Field(default=10, alias="timeoutSeconds", ge=1, le=10)
    output_bytes: int = Field(default=16 * 1024, alias="outputBytes", ge=1, le=16 * 1024)


class CLIDefinition(FrozenModel):
    name: str = Field(min_length=1)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    executable: str = Field(min_length=1)
    subcommand: tuple[str, ...] = Field(min_length=1)
    working_directory: str = Field(alias="workingDirectory", min_length=1)
    environment_names: tuple[str, ...] = Field(alias="environmentNames", default=())
    input_schema: str = Field(alias="inputSchema")
    output_schema: str = Field(alias="outputSchema")
    tool_input_schema: str | None = Field(default=None, alias="toolInputSchema")
    io_format: Literal["json-stdin-stdout"] = Field(default="json-stdin-stdout", alias="ioFormat")


class LoopDefinition(FrozenModel):
    name: Literal["fixed", "research"]
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    stages: tuple[Literal["research", "context", "inference"], ...]
    limits: LoopLimits = Field(default_factory=LoopLimits)


class CapabilityCatalog(ApiModel):
    policy_version: str = Field(default=POLICY_VERSION, alias="policyVersion")
    task_templates: list[str] = Field(default_factory=lambda: [TASK_TEMPLATE_VERSION], alias="taskTemplates")
    cli: list[CLIDefinition]
    tools: list[ToolDefinition]
    loops: list[LoopDefinition]
    planned: list[Literal["cli", "kb_tools", "research"]]
