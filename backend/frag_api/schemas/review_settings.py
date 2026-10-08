"""Nonsecret Review defaults. Source grants remain project-local and explicit."""
from typing import Literal
from pathlib import PurePosixPath, PureWindowsPath
from pydantic import ConfigDict, Field, model_validator
from frag_api.schemas.common import ApiModel
from frag_api.schemas.agents import AgentCheck
from frag_api.schemas.context_source import FileSourceSelection
from frag_api.schemas.harness import PluginEvidenceSelection
from frag_api.schemas.governance import TaskContract
from frag_api.schemas.memory import MemorySelection


class StrictSettings(ApiModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class ChecklistTemplate(StrictSettings):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=500)
    blocking: bool = False


class ApplicationSettings(StrictSettings):
    mode: Literal["files", "retrieval", "plugin"] = "files"
    top_k: Literal[1, 3, 5, 10] = Field(default=3, alias="topK")
    research_in_custom: bool = Field(default=False, alias="researchInCustom")
    checklist: list[ChecklistTemplate] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_items(self):
        if len({item.id for item in self.checklist}) != len(self.checklist):
            raise ValueError("Checklist identifiers must be unique.")
        return self


class EvidenceSettings(StrictSettings):
    mode: Literal["files", "retrieval", "plugin"] = "files"
    file: FileSourceSelection | None = None
    plugin: PluginEvidenceSelection | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def bounded_source(self):
        if (self.mode != "plugin" and self.plugin is not None) or (self.mode == "plugin" and self.file is not None):
            raise ValueError("Select only the chosen evidence mode.")
        if self.synthetic and (self.mode != "retrieval" or self.file is not None):
            raise ValueError("Synthetic retrieval has no personal file selection.")
        if self.file:
            path = self.file.relative_path
            if PureWindowsPath(path).drive or PureWindowsPath(path).root or PurePosixPath(path).is_absolute() or ".." in path.replace("\\", "/").split("/"):
                raise ValueError("Select a relative path inside the bound project.")
            if len(set(self.file.locator_ids)) != len(self.file.locator_ids):
                raise ValueError("Locator identifiers must be distinct.")
        return self

    @property
    def ready(self):
        return bool(self.plugin) if self.mode == "plugin" else self.synthetic or bool(self.file)


class ConversationSettings(StrictSettings):
    evidence: EvidenceSettings
    top_k: Literal[1, 3, 5, 10] = Field(default=3, alias="topK")
    research: bool = False
    checklist: list[ChecklistTemplate] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_strategy(self):
        if self.research and self.evidence.mode == "plugin":
            raise ValueError("Research is not available for plugin evidence.")
        ApplicationSettings(checklist=self.checklist)
        return self


class ApplicationUpdate(StrictSettings):
    revision: int = Field(ge=0)
    settings: ApplicationSettings


class ProjectUpdate(StrictSettings):
    revision: int = Field(ge=0)
    settings: EvidenceSettings


class ConversationUpdate(AgentCheck):
    revision: int = Field(ge=0, strict=True)
    settings: ConversationSettings | None


class SettingsPrepare(AgentCheck):
    application_revision: int = Field(alias="applicationRevision", ge=0, strict=True)
    project_revision: int = Field(alias="projectRevision", ge=0, strict=True)
    conversation_revision: int = Field(alias="conversationRevision", ge=0, strict=True)
    override: ConversationSettings | None = None
    task: TaskContract | None = None
    selected_memory: list[MemorySelection] = Field(default_factory=list, alias="selectedMemory", max_length=3)

