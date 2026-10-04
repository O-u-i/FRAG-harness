"""Observed Research path checks; no causal, semantic or real-model claims."""
from __future__ import annotations

import json
from pydantic import ValidationError

from frag_api.schemas.evaluation import EvalCheck
from frag_api.schemas.research import ResearchDecision
from frag_api.schemas.tools import ReadArguments, SearchArguments


def _check(check_id, category, passed, detail, observed=None):
    return EvalCheck(id=check_id, stage="trajectory", category=category,
                     status="PASS" if passed else "FAIL", detail=detail, observed=observed or {})


def _contains_exact(value, expected):
    if value == expected:
        return True
    if isinstance(value, dict):
        return any(_contains_exact(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_exact(item, expected) for item in value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return False
        return not isinstance(decoded, str) and _contains_exact(decoded, expected)
    return False


def score_trajectory(case, report, calls, gate_checks, restart_checks):
    """Score the actual durable report and captured requests against declared fixtures."""
    research = report.research
    if research is None:
        return [EvalCheck(id="research.missing", stage="trajectory", category="trajectory", status="ERROR",
                          detail="The production runner returned no durable Research state.")]
    tools = report.tool_calls
    names = [item.name for item in tools]
    statuses = [item.status for item in tools]
    expected_statuses = case.expected_tool_statuses or ["completed"] * len(case.expected_tool_names)
    checks = [
        _check("research.termination", "trajectory", research.status == case.expected_status,
               "The production runner must reach the declared bounded termination state.",
               {"expected": case.expected_status, "actual": research.status}),
        _check("research.sequence", "trajectory", names == case.expected_tool_names and statuses == expected_statuses,
               "Observed tool order and durable outcomes must match the declared path.",
               {"expectedNames": case.expected_tool_names, "actualNames": names,
                "expectedStatuses": expected_statuses, "actualStatuses": statuses}),
        _check("research.limits", "host_enforcement", len(calls) <= 3 and len(tools) <= 6
               and research.max_turns == 3 and research.max_tool_calls == 6
               and all(call.request_body()["max_output_tokens"] == 800 and call.max_retries == 0 for call, _ in calls),
               "Research requests use the host's three-turn, six-tool, 800-token and zero-retry limits."),
        _check("research.call_pairing", "trajectory", len({item.call_id for item in tools}) == len(tools)
               and all(item.result.call_id == item.call_id for item in tools if item.result is not None),
               "Tool observations must be unique and pair with their actual callId."),
        _check("research.approval_gate", "host_enforcement", bool(gate_checks) and all(gate_checks),
               "Unapproved execution and approval replay must not create another model call."),
    ]
    successful = {row.evidence_id for item in tools if item.result for row in item.result.evidence}
    proposed = {}
    for index, (call, payload) in enumerate(calls):
        try:
            decision = ResearchDecision.model_validate(payload)
            valid = True
            for item in decision.tool_calls:
                argument_model = {"kb.read": ReadArguments, "kb.search": SearchArguments}.get(item.name)
                if argument_model is None:
                    valid = False
                    continue
                arguments = argument_model.model_validate(item.arguments)
                binding = next((source for source in report.selection.source_bindings
                    if source.identity == arguments.identity and source.revision == arguments.revision), None)
                valid = valid and binding is not None and set(arguments.locator_ids).issubset(binding.locator_ids)
                if isinstance(arguments, ReadArguments):
                    valid = valid and binding is not None and set(arguments.evidence_ids).issubset(binding.evidence_ids)
                proposed[item.call_id] = item
        except ValidationError:
            valid = False
        checks.append(_check(f"research.decision.{index + 1}", "model_quality", valid,
            "The captured scripted proposal must be complete and stay inside the selected tool scope."))
    checks.append(_check("research.execution_scope", "host_enforcement", all(
        item.call_id in proposed and item.name == proposed[item.call_id].name
        and item.arguments == proposed[item.call_id].arguments for item in tools),
        "Executed tool records must correspond to captured complete proposals."))
    requests = {item.prepared_call.fingerprint: item for item in report.requests if item.stage == "research"}
    checks.append(_check("research.request_identity", "host_enforcement", all(
        call.fingerprint in requests and requests[call.fingerprint].prepared_call == call for call, _ in calls),
        "Captured executed requests must be the exact requests retained by the production host."))
    if research.status == "awaiting_context":
        checks.append(_check("research.evidence_selection", "host_enforcement",
            set(research.selected_evidence_ids).issubset(successful),
            "Finish may select only evidence returned by actual selected tools."))
    for index, expected in enumerate(case.required_missing_information):
        checks.append(_check(f"research.missing.{index}", "trajectory",
            any(expected in value for value in research.missing_information),
            "Declared missing information remains explicit.", {"expected": expected}))
    for index, (call, _) in enumerate(calls[1:], 1):
        prior_turn = research.turns[index - 1]
        proposed = {item.call_id for item in prior_turn.decision.tool_calls} if prior_turn.decision else set()
        observations = [item for item in tools if item.call_id in proposed]
        wire = call.request_body()
        passed = bool(observations) and all(
            _contains_exact(wire, item.result.model_dump(by_alias=True)) if item.result else
            _contains_exact(wire, item.error_code) for item in observations)
        checks.append(_check(f"research.result_history.{index}", "trajectory", passed,
            "The next captured exact request contains prior actual tool results or sanitized errors."))
    if case.restart_after_turn is not None:
        checks.append(_check("research.restart", "host_enforcement", bool(restart_checks) and all(restart_checks),
            "Restart restores a reliable checkpoint without dispatch or reusable approval."))
    return checks
