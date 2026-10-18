"""Strict read-only plugin protocol; registration never grants source access."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PLUGIN_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"


def integer_protocol(value):
    if type(value) is not int:
        raise ValueError("Protocol must be an integer.")
    return value


class PluginModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PluginEvidenceRequest(PluginModel):
    protocol_version: Literal[2] = Field(default=2, alias="protocolVersion")
    plugin_id: str = Field(alias="pluginId", pattern=PLUGIN_ID_PATTERN, max_length=63)
    scope_id: str = Field(alias="scopeId", min_length=1, max_length=500)
    record_ids: list[str] = Field(alias="recordIds", min_length=1, max_length=10)

    _integer_protocol = field_validator("protocol_version", mode="before")(integer_protocol)

    @field_validator("record_ids")
    @classmethod
    def selected_ids(cls, values):
        if len(set(values)) != len(values) or any(not value or len(value) > 128 for value in values):
            raise ValueError("Record IDs must be unique bounded strings.")
        return values


class PluginEvidenceRecord(PluginModel):
    record_id: str = Field(alias="recordId", min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=60_000)
    revision: str = Field(min_length=1, max_length=512)


class PluginEvidenceResponse(PluginModel):
    protocol_version: Literal[2] = Field(alias="protocolVersion")
    plugin_id: str = Field(alias="pluginId", pattern=PLUGIN_ID_PATTERN, max_length=63)
    scope_id: str = Field(alias="scopeId", min_length=1, max_length=500)
    records: list[PluginEvidenceRecord] = Field(min_length=1, max_length=10)
    _integer_protocol = field_validator("protocol_version", mode="before")(integer_protocol)

    @model_validator(mode="after")
    def unique_records(self):
        if len({item.record_id for item in self.records}) != len(self.records):
            raise ValueError("Returned record IDs must be unique.")
        return self


class PluginScopeRecord(PluginModel):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=500)


class PluginScope(PluginScopeRecord):
    id: str = Field(min_length=1, max_length=500)
    records: list[PluginScopeRecord] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_records(self):
        if len({item.id for item in self.records}) != len(self.records):
            raise ValueError("Scope record IDs must be unique.")
        return self


class PluginScopes(PluginModel):
    scopes: list[PluginScope] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_scopes(self):
        if len({item.id for item in self.scopes}) != len(self.scopes):
            raise ValueError("Scope IDs must be unique.")
        return self


class FcWorkspace(PluginModel):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=500)
    kind: Literal['personal', 'sandbox']


class FcGrant(PluginModel):
    mode: Literal['all', 'living', 'investment', 'selected']
    itemIds: list[str] = Field(max_length=500)


class FcCatalogItem(PluginModel):
    id: str = Field(pattern=r'^(?:(?:account|asset|plan|arrangement|transfer):[a-f0-9]{32}|report:(?:monthly-review|month-to-date|economic-evidence))$')
    label: str = Field(min_length=1, max_length=500)
    kind: Literal['account', 'asset', 'plan', 'arrangement', 'transfer', 'report']
    segment: Literal['living', 'investment'] | None


class FcConnectionCatalog(PluginModel):
    schemaVersion: Literal[1]
    workspace: FcWorkspace
    readGrant: FcGrant
    items: list[FcCatalogItem] = Field(max_length=500)
    selectedRecordIds: list[str] = Field(max_length=10)

    @model_validator(mode='after')
    def unique_items(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError('Financial item IDs must be distinct.')
        return self
