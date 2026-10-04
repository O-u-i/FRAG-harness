"""Pure proposal checks and deterministic restoration of known research responses."""
from pydantic import ValidationError
from frag_api.errors import PolicyRejectedError, RagOutputError
from frag_api.request_spec import estimated_tokens
from frag_api.schemas.research import ResearchDecision
from frag_api.schemas.tools import ReadArguments, SearchArguments
from frag_api.services.runtime_policy import HostPolicy, redact_value
from frag_api.services.research_native import validate_attempt_native


def validate_decision(report, output, secrets=(), *, restoring=False):
    try:
        decision = ResearchDecision.model_validate(output)
        if estimated_tokens(decision.model_dump(by_alias=True)) > 800 or report.consumed_tokens > report.run_token_limit:
            raise ValueError()
        prior_ids = {item.call_id for item in report.tool_calls}
        if len(prior_ids | {item.call_id for item in decision.tool_calls}) > 6:
            raise ValueError()
        for call in decision.tool_calls:
            if call.name not in ("kb.search", "kb.read") or (call.call_id in prior_ids and not restoring):
                raise ValueError()
            if redact_value(call.call_id, secrets) != call.call_id:
                raise ValueError()
            model = ReadArguments if call.name == "kb.read" else SearchArguments
            arguments = model.model_validate(call.arguments)
            if arguments.identity.kind == "fc_record":
                raise ValueError()
            binding = HostPolicy.require_selected(report.selection.source_bindings,
                arguments.identity, arguments.revision, arguments.locator_ids)
            if isinstance(arguments, ReadArguments):
                allowed = {row.evidence_id for row in report.selection.candidate_evidence
                           if row.evidence_id in binding.evidence_ids and row.locator_id in arguments.locator_ids}
                if not set(arguments.evidence_ids).issubset(allowed):
                    raise ValueError()
        observed = {row.evidence_id for tool in report.tool_calls if tool.status == "completed"
                    for row in tool.result.evidence}
        if not set(decision.evidence_ids).issubset(observed):
            raise ValueError()
        return decision
    except (ValueError, ValidationError, PolicyRejectedError) as error:
        raise RagOutputError() from error


def checkpoint_research(runtime, run_id, call_id, output):
    report = runtime.repository.get(run_id)
    decision = validate_decision(report, output, runtime.redaction_secrets)
    attempt = next(item for item in report.requests if item.id == call_id)
    validate_attempt_native(attempt, decision)
    def change(current):
        call = next(item for item in current.requests if item.id == call_id)
        turn = next(item for item in current.research.turns if item.attempt_id == call_id)
        call.structural_validation = "PASS"
        turn.decision = decision
        current.research.missing_information = list(decision.missing_information)
        if decision.action == "finish":
            turn.status = "completed"
            current.research.selected_evidence_ids = list(decision.evidence_ids)
            current.research.status = "awaiting_context" if decision.evidence_ids else "exhausted"
            status = "ready_context" if decision.evidence_ids else "error"
        else:
            turn.status = "tools_pending"
            current.research.status, status = "ready", "ready_research"
        if current.run.status not in ("paused", "rejected"):
            current.run.status = status
        current.run.active_call_id = None
    return runtime.repository.update(run_id, change)
