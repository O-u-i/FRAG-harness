"""Score one explicitly supplied RunReport; never dispatch, restore or reread a source."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from frag_api.evaluation_scoring import aggregate, contains_literal, coverage, score_facts
from frag_api.providers.prepared import output_model_for
from frag_api.request_spec import estimated_tokens, fingerprint, strict_json
from frag_api.schemas.evaluation import CapturedGold, EvalCaseReport, EvalCheck, EvalReport
from frag_api.schemas.governance import HOST_VERSION, TaskContract, ToolDefinition
from frag_api.schemas.research import ResearchDecision
from frag_api.schemas.runtime import RunReport
from frag_api.schemas.tools import ToolResult
from frag_api.services.governed_context import CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT
from frag_api.services.research_checkpoint import validate_decision
from frag_api.services.research_native import native_history, projected_tools
from frag_api.services.research_requests import validate_history

STATUSES = ("PASS", "FAIL", "ERROR", "NOT_RUN", "UNDETERMINED")
LIMITATIONS = [
    "This evaluation scores supplied original captured artifacts; it makes no model call or source read.",
    "Literal expectations must be written from reviewed source evidence, not inferred from the model answer.",
    "Hash consistency is not independent authenticity, current-source validation or proof of approval.",
    "Human semantic review remains UNDETERMINED here, even when a capture records an accepted review.",
    "No current provider, plugin, memory or live Finance Core compatibility is established by this capture.",
]


def _read(path, limit):
    with Path(path).open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Bounded capture input exceeded.")
    return strict_json(content.decode("utf-8-sig"))


def _check(identifier, stage, category, passed, detail):
    return EvalCheck(id=identifier, stage=stage, category=category,
                     status="PASS" if passed else "FAIL", detail=detail)


def _not_run(identifier, stage, category, detail):
    return EvalCheck(id=identifier, stage=stage, category=category, status="NOT_RUN", detail=detail)


def _research_wire(report, attempt, body, payload, binding, sources):
    """Match stored wire feedback to the already recorded prefix, without executing it."""
    call = attempt.prepared_call
    definitions = [ToolDefinition.model_validate(value) for value in binding["toolVersions"]]
    first_binding = next(item.prepared_call.request_binding() for item in report.requests if item.stage == "research")
    if (len({item.name for item in definitions}) != len(definitions)
            or binding["toolVersions"] != first_binding["toolVersions"]
            or binding.get("researchConfiguration") != report.research.configuration_hash):
        raise ValueError()
    if call.purpose == "research":
        number = payload.get("turn")
        if type(number) is not int or not 1 <= number <= report.research.max_turns:
            raise ValueError()
        turns = [turn for turn in report.research.turns if turn.number < number]
        selected = []
        missing = turns[-1].decision.missing_information if turns and turns[-1].decision else []
    else:
        turns = report.research.turns
        selected, missing = report.research.selected_evidence_ids, report.research.missing_information
    decisions = [turn.decision.model_dump(by_alias=True) for turn in turns if turn.decision]
    prior_ids = {item.call_id for turn in turns if turn.decision for item in turn.decision.tool_calls}
    tools = [item for item in report.tool_calls if item.call_id in prior_ids]
    if (binding.get("researchDigest") != fingerprint({"configurationHash": report.research.configuration_hash,
            "selectedEvidenceIds": selected, "missingInformation": missing, "decisions": decisions})
            or binding.get("trajectoryDigest") != fingerprint([item.model_dump(by_alias=True) for item in tools])):
        raise ValueError()
    if call.purpose != "research":
        if payload.get("researchMissingInformation") != missing:
            raise ValueError()
        return
    if attempt.output is not None and attempt.structural_validation == "PASS":
        prefix = SimpleNamespace(selection=report.selection, tool_calls=tools,
                                 consumed_tokens=report.consumed_tokens, run_token_limit=report.run_token_limit)
        validate_decision(prefix, ResearchDecision.model_validate(attempt.output), restoring=True)
    labels = {row.evidence_id: row.locator_label for row in report.selection.candidate_evidence}
    manifest = [{**source, "descriptions": [{"evidenceId": key, "locatorLabel": labels[key]}
                for key in source["evidenceIds"]]} for source in sources]
    if payload.get("manifest") != manifest:
        raise ValueError()
    if call.transport == "pi-responses-v1":
        registry = SimpleNamespace(catalog=lambda: definitions)
        prefix = SimpleNamespace(research=SimpleNamespace(turns=turns), requests=report.requests, tool_calls=tools)
        if (body.get("parallel_tool_calls") is not False or body.get("tool_choice") != "auto"
                or body.get("tools") != projected_tools(SimpleNamespace(registry=registry))
                or body["input"][1:] != native_history(prefix)):
            raise ValueError()
    else:
        observations = [{"callId": item.call_id, "name": item.name, "status": item.status,
                         "result": item.result.model_dump(by_alias=True) if item.result else None,
                         "errorCode": item.error_code} for item in tools]
        declared_tools = [{"name": item.name, "version": item.version, "readOnly": item.read_only,
                           "inputSchema": strict_json(item.input_schema), "outputContract": "ToolResult"}
                          for item in definitions]
        if (payload.get("decisions") != decisions or payload.get("observations") != observations
                or payload.get("tools") != declared_tools
                or payload.get("toolResultSchema") != ToolResult.model_json_schema(by_alias=True)
                or payload.get("outputSchema") != ResearchDecision.model_json_schema(by_alias=True)):
            raise ValueError()


def _integrity(report):
    """Check recorded links and hashes without constructing an executable runtime."""
    if (report.run.session_id != report.session.id
            or report.snapshot_digest != fingerprint(report.selection.model_dump(by_alias=True))
            or report.consumed_tokens > report.run_token_limit
            or report.run_token_limit > 30_000):
        raise ValueError()
    evidence = {item.evidence_id: item for item in report.selection.candidate_evidence}
    if len(evidence) != len(report.selection.candidate_evidence):
        raise ValueError()
    sources = [item.model_dump(mode="json", by_alias=True) for item in report.selection.source_bindings]
    bound_ids = {key for item in report.selection.source_bindings for key in item.evidence_ids}
    if bound_ids != set(evidence) or any(not any(row.evidence_id in binding.evidence_ids
            and row.locator_id in binding.locator_ids for binding in report.selection.source_bindings)
            for row in evidence.values()):
        raise ValueError()
    if len({item.id for item in report.requests}) != len(report.requests):
        raise ValueError()
    task_versions = [item.model_dump(mode="json", by_alias=True) for item in
                     [report.selection.task, *(review.checklist for review in report.reviews)]]
    selected_memory = report.selection.input.get("selectedMemory", [])
    frozen_memory = None
    for attempt in report.requests:
        call = attempt.prepared_call
        body, binding = strict_json(call.body), strict_json(call.binding)
        limit = {"research": 800, "context": CONTEXT_OUTPUT_LIMIT, "inference": INFERENCE_OUTPUT_LIMIT}[call.purpose]
        if (call.purpose != attempt.stage
                or call.fingerprint != fingerprint(call.model_dump(by_alias=True, exclude={"fingerprint"}))
                or body.get("store") is not False or body.get("model") != call.model
                or call.estimated_input_tokens != estimated_tokens(body)
                or call.estimated_input_tokens > call.input_budget * (100 - call.reserved_percent) // 100
                or binding.get("sources") != sources or call.run_token_limit != report.run_token_limit
                or type(body.get("max_output_tokens")) is not int or not 0 < body["max_output_tokens"] <= limit
                or binding.get("memoryVersions", []) != selected_memory
                or (attempt.output is not None and attempt.output_digest != fingerprint(attempt.output))
                or (attempt.output is None and attempt.output_digest is not None)
                or (attempt.output is not None and attempt.status != "completed")):
            raise ValueError()
        output_model_for(call)
        raw_input = body["input"]
        payload = strict_json(raw_input[0]["content"][0]["text"] if isinstance(raw_input, list) else raw_input)
        task = TaskContract.model_validate(binding["task"])
        memory = payload.get("memory", [])
        if (payload.get("task") != task.model_dump(mode="json", by_alias=True) or binding["task"] not in task_versions
                or (attempt.status == "completed" and task.blocking_ids)
                or [{"memoryId": item["memoryId"], "version": item["version"]} for item in memory] != selected_memory
                or (frozen_memory is not None and memory != frozen_memory)
                or ((call.transport != "pi-responses-v1" or call.purpose != "research") and body.get("tools") != [])):
            raise ValueError()
        frozen_memory = memory
        if report.research:
            _research_wire(report, attempt, body, payload, binding, sources)
        if call.purpose == "context":
            selected = set(report.research.selected_evidence_ids) if report.research else set(evidence)
            expected = [row.model_dump(by_alias=True) for row in evidence.values() if row.evidence_id in selected]
            if payload.get("evidence") != expected or payload.get("goal") != report.selection.goal:
                raise ValueError()
        elif call.purpose == "inference":
            context_fingerprints = {item.prepared_call.fingerprint for item in report.requests
                if item.stage == "context" and item.status == "completed" and item.structural_validation == "PASS"
                and report.context is not None and item.output == report.context.model_dump(by_alias=True)}
            if (report.context is None or payload.get("context") != report.context.model_dump(by_alias=True)
                    or payload.get("query") != report.selection.goal
                    or binding.get("contextFingerprint") not in context_fingerprints):
                raise ValueError()
        elif payload.get("goal") != report.selection.goal:
            raise ValueError()
    for stage, output in (("context", report.context), ("inference", report.model_output)):
        if output is not None and not any(attempt.stage == stage and attempt.status == "completed"
                and attempt.structural_validation == "PASS" and attempt.output == output.model_dump(by_alias=True)
                for attempt in report.requests):
            raise ValueError()
    if report.research:
        first = next(item for item in report.requests if item.stage == "research")
        definitions = {item.name: item for item in (
            ToolDefinition.model_validate(value) for value in first.prepared_call.request_binding()["toolVersions"])}
        # Recorded definitions are validation data; no executable tool binding is registered.
        tools = SimpleNamespace(registry=SimpleNamespace(get=lambda name: SimpleNamespace(definition=definitions[name])))
        validate_history(report, (), tools)
    elif report.tool_calls:
        raise ValueError()
    for revision in report.revisions:
        if revision.content_digest != fingerprint(revision.result.model_dump(by_alias=True)):
            raise ValueError()


def _stage_limit(report, stage, output):
    return min(attempt.prepared_call.request_body()["max_output_tokens"] for attempt in report.requests
               if attempt.stage == stage and attempt.status == "completed"
               and attempt.structural_validation == "PASS" and attempt.output == output.model_dump(by_alias=True))


def _score(gold, report):
    _integrity(report)
    checks = [_check("capture.integrity", "capture", "host_enforcement", True,
                     "Recorded snapshot, request, output and call links have internally consistent hashes.")]
    matches = (gold.goal == report.selection.goal and gold.source_bindings == report.selection.source_bindings
               and (gold.run_id is None or gold.run_id == report.run.id))
    checks.append(_check("gold.source_binding", "source", "host_enforcement", matches,
                         "Gold must match the captured goal and exact source identity, revision, parser and selected scope."))
    checks.extend([
        _not_run("capture.current_source", "source", "host_enforcement", "Source files and current runtime configuration were not reread."),
        _not_run("capture.approval", "approval", "host_enforcement", "Approval tokens are intentionally absent; a saved request does not prove approval."),
        _not_run("retrieval.coverage", "retrieval", "retrieval", "RunReport does not record the original complete retrieval ranking."),
    ])
    if report.research:
        checks.append(_check("research.history", "trajectory", "trajectory", True,
                             "Stored decisions, bounded tools, callId results and selected observations are consistent."))
    else:
        checks.append(_not_run("research.history", "trajectory", "trajectory", "This capture has no Research trajectory."))
    if matches:
        rows = report.selection.candidate_evidence
        checks.append(coverage(gold.expected_evidence_ids, [row.evidence_id for row in rows], "evidence", "evidence"))
        checks.extend(score_facts(" ".join(row.text for row in rows), gold.facts, "evidence", "evidence"))
        if report.context is not None:
            ids = [item.evidence_id for item in report.context.evidence]
            allowed = set(report.research.selected_evidence_ids) if report.research else {row.evidence_id for row in rows}
            checks.append(_check("context.identifiers", "context", "model_quality", set(ids) == allowed and len(ids) == len(set(ids)),
                                 "Original Context must retain exactly the supplied unique evidence IDs."))
            checks.append(coverage(gold.expected_evidence_ids, ids, "context", "model_quality"))
            text = " ".join(item.summary + " " + " ".join(item.preserved_facts) for item in report.context.evidence)
            checks.extend(score_facts(text, gold.facts, "context"))
            checks.append(_check("context.limit", "context", "model_quality",
                                 estimated_tokens(report.context.model_dump(by_alias=True)) <= _stage_limit(report, "context", report.context),
                                 "Original structured Context remains within the recorded stage cap."))
        else:
            checks.append(_not_run("context.execution", "context", "model_quality", "No reliably checkpointed original Context is available."))
        if report.model_output is not None:
            answer = report.model_output
            allowed = {row.evidence_id for row in report.context.evidence} if report.context else set()
            cited = {key for claim in answer.claims for key in claim.evidence_ids}
            checks.append(_check("citation.identifiers", "citation", "model_quality", bool(cited) and cited.issubset(allowed),
                                 "Original claim citation IDs must belong to the original Context; membership is not semantic support."))
            checks.extend(score_facts(answer.answer + " " + " ".join(item.text for item in answer.claims), gold.facts, "inference"))
            checks.append(_check("inference.limit", "inference", "model_quality",
                                 estimated_tokens(answer.model_dump(by_alias=True)) <= _stage_limit(report, "inference", answer),
                                 "Original structured answer remains within the recorded stage cap."))
        else:
            checks.append(_not_run("inference.execution", "inference", "model_quality", "No reliably checkpointed original model answer is available."))
        for stage, output in (("context", report.context), ("inference", report.model_output)):
            if output is not None:
                for index, expected in enumerate(gold.required_missing_information):
                    checks.append(_check(f"{stage}.missing.{index}", stage, "model_quality",
                        any(contains_literal(item, expected) for item in output.missing_information),
                        "Declared missing information must remain explicit in the original saved artifact."))
    else:
        checks.append(_not_run("model.scoring", "model", "model_quality", "Gold source/goal mismatch blocks scoring this capture against unrelated expectations."))
    unknown = report.run.status == "outcome_unknown" or any(item.status in ("outcome_unknown", "dispatching")
        for item in [*report.requests, *report.tool_calls])
    if unknown:
        checks.append(EvalCheck(id="capture.outcome", stage="model", category="model_quality", status="UNDETERMINED",
                               detail="An external-call outcome is unknown; this evaluator never resends it."))
    checks.append(EvalCheck(id="semantic.review", stage="semantic", category="semantic_review", status="UNDETERMINED",
                           detail="Declared literal checks cannot establish factual support or validate a recorded human decision."))
    model_checks = [item.status for item in checks if item.category == "model_quality"]
    model_status = aggregate(model_checks)
    if model_status not in ("ERROR", "FAIL") and (not matches or report.context is None or report.model_output is None or unknown):
        model_status = "UNDETERMINED" if unknown else "NOT_RUN"
    status = aggregate([item.status for item in checks])
    if status not in ("ERROR", "FAIL"):
        status = model_status
    failures = [item for item in checks if item.status == "FAIL"]
    return EvalCaseReport(id=gold.suite_id, query=gold.goal, status=status,
        hostEnforcementStatus=aggregate([item.status for item in checks if item.category == "host_enforcement"]),
        modelQualityStatus=model_status, earliestObservedDeviation=failures[0].stage if failures else None,
        secondaryObservedFailures=[item.id for item in failures[1:]], checks=checks,
        trace={"capture":report.model_dump(mode="json", by_alias=True), "recordedHumanSemanticReview":report.semantic_review})


def score_capture(gold_path: str | Path, capture_path: str | Path) -> EvalReport:
    """Explicit input files only; returns a report without writing files or calling providers."""
    gold = None
    try:
        gold = CapturedGold.model_validate(_read(gold_path, 1_000_000))
        report = RunReport.model_validate(_read(capture_path, 5_000_000))
        case = _score(gold, report)
        counts = Counter(item.status for item in case.checks)
        return EvalReport(hostVersion=HOST_VERSION, runnerVersion="1.2.0", provider="captured-artifacts",
            suiteId=gold.suite_id, suiteVersion=gold.suite_version, status=case.status, cases=[case],
            trajectoryStatus=aggregate([item.status for item in case.checks if item.category == "trajectory"]),
            counts={status:counts[status] for status in STATUSES}, limitations=LIMITATIONS)
    except Exception:
        return EvalReport(hostVersion=HOST_VERSION, runnerVersion="1.2.0", provider="captured-artifacts",
            suiteId=gold.suite_id if gold else None, suiteVersion=gold.suite_version if gold else None,
            status="ERROR", cases=[], counts={status:int(status == "ERROR") for status in STATUSES},
            errors=["Captured Gold/report schema, integrity or scorer failed; no result is inferred and no call was retried."],
            limitations=LIMITATIONS)
