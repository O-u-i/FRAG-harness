from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


SourceFormat = Literal["md", "txt", "pdf", "docx", "csv", "xlsx", "html"]
LocatorKind = Literal["document", "section", "page", "rows", "sheet"]
ParseStatus = Literal["ready", "unsupported", "too_large", "error"]


class LocalFileSource(ApiModel):
    relative_path: str = Field(alias="relativePath")
    category: str
    format: SourceFormat | None
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    modified_at: str = Field(alias="modifiedAt")
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    status: ParseStatus
    status_reason: str | None = Field(default=None, alias="statusReason")


class SourceLocator(ApiModel):
    id: str
    kind: LocatorKind
    label: str
    excerpt: str


class LocalFileInspectRequest(ApiModel):
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=500)


class LocalFileInspectResponse(ApiModel):
    source: LocalFileSource
    locators: list[SourceLocator]
    warnings: list[str]


class FileSourceSelection(ApiModel):
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=500)
    locator_ids: list[str] = Field(alias="locatorIds", min_length=1, max_length=20)
    relevance_reason: str = Field(alias="relevanceReason", min_length=3, max_length=500)


class ExtractedSection(ApiModel):
    locator: SourceLocator
    text: str


class ParsedLocalFile(ApiModel):
    source: LocalFileSource
    sections: list[ExtractedSection]
    warnings: list[str]
