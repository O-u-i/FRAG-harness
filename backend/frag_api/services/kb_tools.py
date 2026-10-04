"""Real selected KB tools: native lexical search and a governed CLI snapshot read."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from pydantic import ValidationError
from frag_api.errors import PolicyRejectedError, RequestContractError, RuntimeConflictError
from frag_api.request_spec import fingerprint
from frag_api.schemas.governance import CLIDefinition, ToolDefinition
from frag_api.schemas.harness import HarnessRequest
from frag_api.schemas.rag import RagQueryRequest
from frag_api.schemas.tools import ReadArguments, ReadCarrierInput, SearchArguments, ToolCallRecord, ToolResult
from frag_api.services.cli_executor import ControlledCLI, ToolExecutionError
from frag_api.services.runtime_policy import HostPolicy, redact_value
from frag_api.services.runtime_service import now


def schema(model):
    return json.dumps(model.model_json_schema(by_alias=True), sort_keys=True, separators=(",", ":"))


class KBTools:
    def __init__(self, runtime, harness, rag):
        self.runtime, self.services = runtime, {"harness": harness, "rag": rag}
        self.registry, self.cli_registry = harness.tool_registry, harness.cli_registry
        backend = Path(__file__).resolve().parents[2]
        cli = CLIDefinition(name="kb.read.cli", version="1.0.0", executable=str(Path(sys.executable).resolve()),
            subcommand=("-I", str(backend / "frag_api/tool_worker.py"), "read"), workingDirectory=str(backend),
            environmentNames=("SYSTEMROOT", "WINDIR", "TEMP", "TMP"), inputSchema=schema(ReadCarrierInput),
            toolInputSchema=schema(ReadArguments), outputSchema=schema(ToolResult))
        carrier = ControlledCLI(cli, allowed_working_root=backend)
        self.cli_registry.register(cli, carrier.execute)
        for name, model, transport in (("kb.search", SearchArguments, "native"), ("kb.read", ReadArguments, "cli")):
            self.registry.register(ToolDefinition(name=name, version="1.0.0", inputSchema=schema(model), outputSchema=schema(ToolResult),
                sourceKinds=("local_file", "synthetic"), carrier=transport, carrierId="kb.read.cli" if transport == "cli" else "selected-lexical-v1"),
                input_model=model, output_model=ToolResult,
                execute=self._read if transport == "cli" else self._search, cli_registry=self.cli_registry)

    def _read(self, payload):
        return ToolResult.model_validate(self.cli_registry.get("kb.read.cli").execute(payload))

    @staticmethod
    def _search(payload):
        query = payload["arguments"]["query"].strip().casefold()
        terms = query.split()
        scored = [(sum(term in row["text"].casefold() for term in terms), row) for row in payload["evidence"]]
        rows = [row for score, row in sorted(scored, key=lambda pair: (-pair[0], pair[1]["evidenceId"])) if score]
        rows = rows[:payload["arguments"]["limit"]]
        return ToolResult(callId=payload["callId"], evidence=rows,
            missingInformation=[] if rows else ["No selected evidence matched this lexical query."])

    def _selected(self, report, source_request, *, research=False):
        if report.run.status != ("ready_research" if research else "ready_context") or bool(report.research) != research:
            raise RuntimeConflictError()
        if fingerprint(report.selection.model_dump(by_alias=True)) != report.snapshot_digest:
            raise RuntimeConflictError()
        service = self.services[report.run.kind]
        model = HarnessRequest if report.run.kind == "harness" else RagQueryRequest
        try:
            source = model.model_validate(source_request)
        except ValidationError as error:
            raise RequestContractError([]) from error
        if research:
            return service.research.validate_source(report, source)
        # Never touch FC/plugin routes as part of KB tools, including mixed selections.
        if any(binding.identity.kind == "fc_record" for binding in report.selection.source_bindings):
            raise PolicyRejectedError()
        if (redact_value(source.model_dump(by_alias=True), self.runtime.redaction_secrets) != report.selection.input
                or any(item.status == "dispatching" or (item.status == "completed" and item.structural_validation == "UNDETERMINED") for item in report.requests)):
            raise RuntimeConflictError()
        fresh = service.flow.prepare_preview(source)  # No token, journal mutation or model dispatch.
        first = next(call for call in report.requests if call.stage == "context")
        if (not service.flow._same_recovery_spec(first.prepared_call, fresh.prepared_call)
                or list(fresh.source_bindings) != list(report.selection.source_bindings)
                or fresh.candidate_evidence != report.selection.candidate_evidence):
            raise RuntimeConflictError()
        HostPolicy.require_task(report.reviews[-1].checklist if report.reviews else report.selection.task)
        return fresh

    def execute(self, run_id, source_request, call, *, research=False):
        if redact_value(call.call_id, self.runtime.redaction_secrets) != call.call_id:
            raise PolicyRejectedError()
        report = self.runtime.repository.get(run_id)
        tool = self.registry.get(call.name)
        try:
            arguments = tool.input_model.model_validate(call.arguments)
        except ValidationError as error:
            raise RequestContractError([]) from error
        binding = HostPolicy.require_tool(tool.definition, frozenset(("kb.search", "kb.read")),
            report.selection.source_bindings, arguments.identity, arguments.revision, arguments.locator_ids)
        fresh = self._selected(report, source_request, research=research)
        if research and not any(turn.status == "tools_pending" and call in turn.decision.tool_calls for turn in report.research.turns):
            raise PolicyRejectedError()
        evidence = [row for row in fresh.candidate_evidence
                    if row.evidence_id in binding.evidence_ids and row.locator_id in arguments.locator_ids]
        if isinstance(arguments, ReadArguments):
            if not set(arguments.evidence_ids).issubset({row.evidence_id for row in evidence}):
                raise PolicyRejectedError()
            evidence = [row for row in evidence if row.evidence_id in arguments.evidence_ids]
        payload = {"callId": call.call_id, "arguments": arguments.model_dump(by_alias=True),
                   "evidence": [row.model_dump(by_alias=True) for row in evidence]}
        record = ToolCallRecord(callId=call.call_id, name=call.name, toolVersion=tool.definition.version,
            carrier=tool.definition.carrier, arguments=redact_value(call.arguments, self.runtime.redaction_secrets),
            status="dispatching", createdAt=now())
        def claim(current):
            if (current.run.status != ("ready_research" if research else "ready_context") or current.run.version != report.run.version
                    or any(item.status == "dispatching" for item in current.requests)
                    or len(current.tool_calls) >= 6 or any(item.call_id == call.call_id or item.status in ("dispatching", "outcome_unknown") for item in current.tool_calls)):
                raise RuntimeConflictError()
            current.tool_calls.append(record)
            current.run.updated_at = now()
        self.runtime.repository.update(run_id, claim)
        started = time.monotonic()
        try:
            result = tool.output_model.model_validate(tool.execute(payload))
            allowed = {row.evidence_id: row for row in evidence}
            if (result.call_id != call.call_id or len({row.evidence_id for row in result.evidence}) != len(result.evidence)
                    or any(allowed.get(row.evidence_id) != row for row in result.evidence)
                    or (isinstance(arguments, ReadArguments) and {row.evidence_id for row in result.evidence} != set(arguments.evidence_ids))):
                raise ToolExecutionError("TOOL_RESULT_INVALID")
            safe = ToolResult.model_validate(redact_value(result.model_dump(by_alias=True), self.runtime.redaction_secrets))
            if len(safe.model_dump_json(by_alias=True).encode("utf-8")) > tool.definition.output_bytes:
                raise ToolExecutionError("TOOL_OUTPUT_LIMIT")
            if time.monotonic() - started > tool.definition.timeout_seconds:
                raise ToolExecutionError("TOOL_TIMEOUT")
            record.status, record.result = "completed", safe
        except Exception as error:
            record.status = "failed"
            record.error_code = error.code if isinstance(error, ToolExecutionError) else "TOOL_RESULT_INVALID"
        record.finished_at, record.duration_ms = now(), max(0, int((time.monotonic() - started) * 1000))
        def finish(current):
            item = next(item for item in current.tool_calls if item.call_id == call.call_id)
            if item.status != "dispatching":
                raise RuntimeConflictError()
            current.tool_calls[current.tool_calls.index(item)] = record
            current.run.updated_at = now()
        self.runtime.repository.update(run_id, finish)
        return record
