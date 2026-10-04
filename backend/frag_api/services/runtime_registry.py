"""Versioned registrations require executable bindings; policy remains a separate gate."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from frag_api.errors import PolicyRejectedError
from frag_api.schemas.governance import CLIDefinition, LoopDefinition, ToolDefinition


class LoopRunner(Protocol):
    def preview(self, source_request: Any, *, issue_approval: bool = True) -> Any: ...
    def run_context(self, source_request: Any, request: Any) -> Any: ...
    def run_inference(self, request: Any) -> Any: ...


class ResearchLoopRunner(Protocol):
    def start(self, kind: str, source: Any) -> Any: ...
    def preview(self, run_id: str, source: Any) -> Any: ...
    def execute(self, run_id: str, source: Any, fingerprint: str, token: str) -> Any: ...


@dataclass(frozen=True)
class ToolBinding:
    definition: ToolDefinition
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    execute: Callable[[BaseModel], BaseModel]


@dataclass(frozen=True)
class CLIBinding:
    definition: CLIDefinition
    execute: Callable[[dict], dict]


@dataclass(frozen=True)
class LoopBinding:
    definition: LoopDefinition
    runner: LoopRunner | ResearchLoopRunner


def _schema_matches(text: str, model: type[BaseModel]) -> bool:
    return json.loads(text) == model.model_json_schema(by_alias=True)


class ToolRegistry:
    def __init__(self):
        self._bindings: dict[str, ToolBinding] = {}

    def register(self, definition: ToolDefinition, *, input_model: type[BaseModel],
                 output_model: type[BaseModel], execute: Callable, cli_registry: "CLIRegistry | None" = None) -> None:
        if (definition.name in self._bindings or not callable(execute)
                or not _schema_matches(definition.input_schema, input_model)
                or not _schema_matches(definition.output_schema, output_model)):
            raise ValueError("Tool registration requires unique, schema-compatible executable bindings.")
        if definition.carrier == "cli":
            if cli_registry is None:
                raise ValueError("A CLI carrier requires an executable CLI registration.")
            cli = cli_registry.get(definition.carrier_id)
            if (json.loads(cli.definition.tool_input_schema or cli.definition.input_schema) != json.loads(definition.input_schema)
                    or json.loads(cli.definition.output_schema) != json.loads(definition.output_schema)):
                raise ValueError("Tool and CLI schemas must match.")
        self._bindings[definition.name] = ToolBinding(definition, input_model, output_model, execute)

    def get(self, name: str) -> ToolBinding:
        try:
            return self._bindings[name]
        except KeyError as error:
            raise PolicyRejectedError() from error

    def catalog(self) -> list[ToolDefinition]:
        return [binding.definition for binding in self._bindings.values()]


class CLIRegistry:
    def __init__(self):
        self._bindings: dict[str, CLIBinding] = {}

    def register(self, definition: CLIDefinition, execute: Callable) -> None:
        executable, directory = Path(definition.executable), Path(definition.working_directory)
        if (definition.name in self._bindings or not callable(execute)
                or not executable.is_absolute() or not executable.is_file()
                or not directory.is_absolute() or not directory.is_dir()
                or not all(isinstance(json.loads(schema), dict) for schema in (definition.input_schema, definition.output_schema))):
            raise ValueError("CLI registration requires a fixed executable, directory, schemas and binding.")
        self._bindings[definition.name] = CLIBinding(definition, execute)

    def get(self, name: str) -> CLIBinding:
        try:
            return self._bindings[name]
        except KeyError as error:
            raise PolicyRejectedError() from error

    def catalog(self) -> list[CLIDefinition]:
        return [binding.definition for binding in self._bindings.values()]


class LoopRegistry:
    def __init__(self):
        self._bindings: dict[str, LoopBinding] = {}

    def register(self, definition: LoopDefinition, runner: LoopRunner | ResearchLoopRunner) -> None:
        methods = ("start", "preview", "execute") if definition.name == "research" else ("preview", "run_context", "run_inference")
        if (definition.name in self._bindings
                or not all(callable(getattr(runner, name, None)) for name in methods)):
            raise ValueError("Loop registration requires a unique executable runner.")
        self._bindings[definition.name] = LoopBinding(definition, runner)

    def get(self, name: str) -> LoopBinding:
        try:
            return self._bindings[name]
        except KeyError as error:
            raise PolicyRejectedError() from error

    def catalog(self) -> list[LoopDefinition]:
        return [binding.definition for binding in self._bindings.values()]
