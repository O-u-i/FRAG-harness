"""Offline synthetic evaluation using the production fixed flow and host validators."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError

from frag_api.errors import PolicyRejectedError, RagOutputError
from frag_api.evaluation_scoring import aggregate, contains_literal, coverage, score_facts
from frag_api.providers.llm import FakeLlmProvider, LlmCallResult, LlmSettings, LlmStageSettings
from frag_api.providers.prepared import strict_json, verify_prepared
from frag_api.repositories.rag_index_repository import RagIndexRepository
from frag_api.schemas.evaluation import EvalCaseReport, EvalCheck, EvalReport, GoldCase, GoldSuite
from frag_api.schemas.governance import HOST_VERSION, SourceBinding, SourceIdentity
from frag_api.schemas.rag import InferenceRunRequest, RagDatasetRequest, RagQueryRequest, RagRunRequest
from frag_api.services.context_source_service import ContextSourceService
from frag_api.services.rag_service import DATASET_ID, SOURCE_FILE, RagService
from frag_api.services.governed_context import CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT, estimated_tokens
from frag_api.services.runtime_policy import HostPolicy
from frag_api.services.runtime_registry import CLIRegistry, ToolRegistry

STATUSES = ("PASS", "FAIL", "ERROR", "NOT_RUN", "UNDETERMINED")


class ScriptedProvider(FakeLlmProvider):
    """Only a verified fake request can execute; samples never select a network provider."""
    def __init__(self, settings, sample):
        self.settings, self.sample = settings, sample
        self.calls = []

    def execute_prepared(self, call):
        verify_prepared(call, self.settings)
        generated = super().execute_prepared(call)
        result = LlmCallResult(self.sample or generated.output, generated.usage)
        self.calls.append((call, result))
        return result


def _check(check_id, stage, category, passed, detail, observed=None):
    return EvalCheck(id=check_id, stage=stage, category=category, status="PASS" if passed else "FAIL",
                     detail=detail, observed=observed or {})


def _policy_checks(binding: SourceBinding) -> list[EvalCheck]:
    HostPolicy.require_selected((binding,), binding.identity, binding.revision, binding.locator_ids)
    checks = [_check("policy.selected", "policy", "host_enforcement", True, "Production policy allowed selected read scope.")]
    for name, identity, revision, locators in (
        ("locator_escape", binding.identity, binding.revision, ("not-selected-locator",)),
        ("revision_change", binding.identity, binding.revision + "-changed", binding.locator_ids),
        ("source_escape", SourceIdentity(kind="synthetic", namespace="not-selected", resourceId="other"),
         binding.revision, binding.locator_ids),
    ):
        try:
            HostPolicy.require_selected((binding,), identity, revision, locators)
        except PolicyRejectedError:
            rejected = True
        else:
            rejected = False
        checks.append(_check(f"policy.{name}", "policy", "host_enforcement", rejected,
                             "Production policy must reject this synthetic scope expansion."))
    return checks


def _not_run(check_id, stage, detail):
    return EvalCheck(id=check_id, stage=stage, category="model_quality", status="NOT_RUN", detail=detail)


def _tools(case, preview, checks, trace):
    """Exercise trusted synthetic fixtures through real registered production bindings."""
    from frag_api.services.kb_tools import KBTools
    from frag_api.services.cli_executor import ToolExecutionError
    fixture_host = SimpleNamespace(cli_registry=CLIRegistry(), tool_registry=ToolRegistry())
    tools = KBTools(None, fixture_host, None)
    binding = preview.source_bindings[0]
    rows = [item.model_dump(by_alias=True) for item in preview.candidate_evidence]
    scope = {"identity": binding.identity.model_dump(by_alias=True), "revision": binding.revision,
             "locatorIds": list(binding.locator_ids)}
    observations = []
    for name, extra, empty in (
        ("kb.read", {"evidenceIds": list(binding.evidence_ids)}, False),
        ("kb.search", {"query": case.query, "limit": 10}, False),
        ("kb.search", {"query": "quasar heliosphere", "limit": 10}, True),
    ):
        call_id = f"eval-{uuid4().hex}"
        tool = tools.registry.get(name)
        try:
            arguments = tool.input_model.model_validate({**scope, **extra})
            HostPolicy.require_tool(tool.definition, frozenset(("kb.read", "kb.search")),
                                    preview.source_bindings, arguments.identity, arguments.revision, arguments.locator_ids)
            result = tool.output_model.model_validate(tool.execute({"callId": call_id,
                "arguments": arguments.model_dump(by_alias=True), "evidence": rows}))
            allowed = {item["evidenceId"]: item for item in rows}
            returned = [item.model_dump(by_alias=True) for item in result.evidence]
            valid = (result.call_id == call_id and all(allowed.get(item["evidenceId"]) == item for item in returned)
                     and len({item["evidenceId"] for item in returned}) == len(returned)
                     and (bool(result.missing_information) and not returned if empty else
                          set(allowed) == {item["evidenceId"] for item in returned} if name == "kb.read" else bool(returned)))
            observations.append({"callId": call_id, "name": name, "carrier": tool.definition.carrier,
                                 "toolVersion": tool.definition.version, "result": result.model_dump(by_alias=True)})
            checks.append(_check(f"tool.{name}.{'zero_hit' if empty else 'selected'}", "tool", "tool", valid,
                                 "Registered production binding must return the same callId and selected synthetic evidence."))
        except Exception as error:
            checks.append(EvalCheck(id=f"tool.{name}.execution", stage="tool", category="tool", status="ERROR",
                detail="Registered production tool fixture failed.",
                observed={"code": error.code if isinstance(error, ToolExecutionError) else "TOOL_FIXTURE_ERROR"}))
    trace["tools"] = observations


def _full(case, service, preview, checks, trace):
    service.context_provider = ScriptedProvider(service.settings.context, case.sample_context)
    service.inference_provider = ScriptedProvider(service.settings.inference, case.sample_answer)
    token = preview.approval_token
    run_request = RagRunRequest(**{"datasetId": DATASET_ID, "query": case.query, "topK": case.top_k,
                                 "contextFingerprint": preview.context_fingerprint,
                                 "approvalToken": token, "approved": True})
    # The approval is issued and consumed by the actual host, only for an offline synthetic fixture.
    try:
        context = service.run(run_request)
    except RagOutputError:
        context = None
    prepared, context_call = service.context_provider.calls[-1]
    compressed = context_call.output
    trace["contextRequest"] = prepared.model_dump(by_alias=True)
    trace["contextOutput"] = compressed.model_dump(by_alias=True)
    allowed = {item.evidence_id for item in preview.candidate_evidence}
    returned = [item.evidence_id for item in compressed.evidence]
    ids_valid = set(returned) == allowed and len(returned) == len(set(returned))
    checks.append(_check("context.identifiers", "context", "model_quality", ids_valid,
                         "Context must preserve exactly the supplied unique evidence IDs.", {"evidenceIds": returned}))
    context_bounded = estimated_tokens(compressed.model_dump(by_alias=True)) <= CONTEXT_OUTPUT_LIMIT
    checks.append(_check("context.limit", "context", "model_quality", context_bounded,
                         "Structured Context output must fit the production token cap."))
    context_text = " ".join(item.summary + " " + " ".join(item.preserved_facts) for item in compressed.evidence)
    checks.extend(score_facts(context_text, case.facts, "context"))
    if context is None:
        checks.append(_check("host.context", "context", "host_enforcement", not (ids_valid and context_bounded),
                             "Production fixed runner rejected the scripted Context output."))
        checks.append(_not_run("inference.execution", "inference", "Context was rejected before Inference execution."))
        return
    checks.append(_check("host.context", "context", "host_enforcement", ids_valid and context_bounded,
                         "Production fixed runner accepted this Context output."))
    second = context.inference_preview
    inference_request = InferenceRunRequest(contextFingerprint=preview.context_fingerprint,
        inferenceFingerprint=second.inference_fingerprint, approvalToken=second.approval_token, approved=True)
    try:
        service.run_inference(inference_request)
    except RagOutputError:
        answer_accepted = False
    else:
        answer_accepted = True
    prepared, answer_call = service.inference_provider.calls[-1]
    answer = answer_call.output
    trace["inferenceRequest"] = prepared.model_dump(by_alias=True)
    trace["inferenceOutput"] = answer.model_dump(by_alias=True)
    cited = [evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids]
    citation_valid = bool(cited) and set(cited).issubset(set(returned))
    checks.append(_check("citation.identifiers", "citation", "model_quality", citation_valid,
                         "Citation membership is structural; it does not establish semantic support.",
                         {"allowedIds": returned, "citedIds": cited}))
    answer_bounded = estimated_tokens(answer.model_dump(by_alias=True)) <= INFERENCE_OUTPUT_LIMIT
    checks.append(_check("inference.limit", "inference", "model_quality", answer_bounded,
                         "Structured Inference output must fit the production token cap."))
    checks.extend(score_facts(answer.answer + " " + " ".join(claim.text for claim in answer.claims), case.facts, "inference"))
    for index, expected in enumerate(case.required_missing_information):
        found = any(contains_literal(value, expected) for value in answer.missing_information)
        checks.append(_check(f"inference.missing.{index}", "inference", "model_quality", found,
                             "Declared missing information must remain explicit.", {"expected": expected}))
    if not answer_accepted:
        checks.append(_check("host.citation", "citation", "host_enforcement", not (citation_valid and answer_bounded),
                             "Production fixed runner rejected the scripted Inference output."))
    else:
        checks.append(_check("host.citation", "citation", "host_enforcement", citation_valid and answer_bounded,
                             "Production fixed runner accepted this Inference output."))


def _case(case: GoldCase, service: RagService) -> EvalCaseReport:
    checks, trace = [], {}
    try:
        request = RagQueryRequest(datasetId=DATASET_ID, query=case.query, topK=case.top_k)
        search = service.search(request)
        preview = service.preview(request, issue_approval=case.mode == "full")
        trace.update({"indexRevision": preview.index_revision, "retrieval": search.model_dump(by_alias=True),
                      "evidence": [item.model_dump(by_alias=True) for item in preview.candidate_evidence]})
        checks.append(coverage(case.expected_chunk_ids, [item.chunk_id for item in search.results], "retrieval"))
        checks.append(coverage(case.expected_evidence_ids, [item.evidence_id for item in preview.candidate_evidence],
                               "evidence", "evidence"))
        checks.extend(score_facts(" ".join(item.text for item in preview.candidate_evidence), case.facts, "evidence", "evidence"))
        if preview.source_bindings:
            checks.extend(_policy_checks(preview.source_bindings[0]))
            if case.evaluate_tools:
                _tools(case, preview, checks, trace)
        else:
            checks.append(EvalCheck(id="policy.selected", stage="policy", category="host_enforcement", status="NOT_RUN",
                                    detail="No source evidence was selected; tool authorization was not attempted."))
        if case.mode == "full" and preview.can_approve:
            _full(case, service, preview, checks, trace)
        else:
            reason = ("Retrieval-only case; no model stages were requested." if case.mode == "retrieval"
                      else "No evidence was retrieved; the production host did not issue model approval.")
            checks.append(_not_run("context.execution", "context", reason))
            checks.append(_not_run("inference.execution", "inference", reason))
    except Exception:
        checks.append(EvalCheck(id="runner.error", stage="evaluation", category="host_enforcement", status="ERROR",
                                detail="Execution or scorer failed; no PASS is inferred from an exception."))
    checks.extend([
        EvalCheck(id="semantic.review", stage="semantic", category="semantic_review", status="UNDETERMINED",
                  detail="Human review of semantic support and real model quality was not performed."),
        EvalCheck(id="research.trajectory", stage="trajectory", category="trajectory", status="NOT_RUN",
                  detail="This fixed-flow case did not request a Research trajectory."),
    ])
    failures = [check for check in checks if check.status == "FAIL"]
    return EvalCaseReport(id=case.id, query=case.query, status=aggregate([item.status for item in checks]),
        hostEnforcementStatus=aggregate([item.status for item in checks if item.category == "host_enforcement"]),
        modelQualityStatus=aggregate([item.status for item in checks if item.category == "model_quality"]),
        earliestObservedDeviation=failures[0].stage if failures else None,
        secondaryObservedFailures=[item.id for item in failures[1:]], checks=checks, trace=trace)


def run_gold(path: str | Path, *, work_dir: str | Path | None = None) -> EvalReport:
    """Read one explicit synthetic Gold; write only a fresh local work directory, never delete it."""
    suite = None
    try:
        gold_path = Path(path)
        if gold_path.stat().st_size > 1_000_000:
            raise ValueError("Gold exceeds the bounded input size.")
        suite = GoldSuite.model_validate(strict_json(gold_path.read_text(encoding="utf-8")))
        source_hash = hashlib.sha256(suite.source.markdown.encode("utf-8")).hexdigest()
        if source_hash != suite.source.sha256:
            raise ValueError("Gold source hash does not match.")
        parents, chunks = RagService._chunks_for(suite.source.markdown)
        chunk_ids, evidence_ids = {item.chunk_id for item in chunks}, {item.parent_id for item in parents}
        for case in suite.cases:
            if not set(case.expected_chunk_ids).issubset(chunk_ids) or not set(case.expected_evidence_ids).issubset(evidence_ids):
                raise ValueError("Gold references identifiers absent from its versioned source.")
        base = Path(work_dir) if work_dir else Path(__file__).resolve().parents[2] / ".tmp" / "offline-eval"
        workspace = base / f"run-{uuid4().hex}"
        workspace.mkdir(parents=True, exist_ok=False)
        source_root = workspace / "source"
        source_root.mkdir()
        (source_root / SOURCE_FILE).write_text(suite.source.markdown, encoding="utf-8", newline="")
        stage = LlmStageSettings("fake", "offline-scripted-fake-v1", None, None, 120)
        service = RagService(ContextSourceService(source_root), RagIndexRepository(workspace / "index.sqlite3"),
                             LlmSettings(context=stage, inference=stage))
        service.rebuild(RagDatasetRequest(datasetId=DATASET_ID))
        cases = [_case(case, service) for case in suite.cases]
        if suite.research_cases:
            from frag_api.research_evaluation import evaluate_research
            cases.extend(evaluate_research(case, service, workspace) for case in suite.research_cases)
        counts = Counter(check.status for case in cases for check in case.checks)
        return EvalReport(hostVersion=HOST_VERSION, suiteId=suite.suite_id, suiteVersion=suite.suite_version,
                          sourceRevision=suite.source.revision, sourceHash=source_hash,
                          status=aggregate([case.status for case in cases]), cases=cases,
                          trajectoryStatus=aggregate([check.status for case in cases for check in case.checks
                                                      if check.category == "trajectory"]),
                          counts={status: counts[status] for status in STATUSES})
    except (OSError, ValueError, ValidationError):
        return EvalReport(hostVersion=HOST_VERSION, suiteId=suite.suite_id if suite else None,
                          suiteVersion=suite.suite_version if suite else None, status="ERROR", cases=[],
                          counts={status: int(status == "ERROR") for status in STATUSES},
                          errors=["Invalid or unreadable versioned synthetic Gold; execution did not complete."])
    except Exception:
        return EvalReport(hostVersion=HOST_VERSION, status="ERROR", cases=[],
                          counts={status: int(status == "ERROR") for status in STATUSES},
                          errors=["Offline runner failed; execution did not complete."])


def render_markdown(report: EvalReport) -> str:
    def cell(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = [f"# Offline evaluation: {report.suite_id or 'invalid Gold'}", "", f"Status: {report.status}", "",
             "| Case | Status | Host enforcement | Model artifacts | Earliest observed deviation |",
             "| --- | --- | --- | --- | --- |"]
    lines.extend(f"| {cell(case.id)} | {case.status} | {case.host_enforcement_status} | {case.model_quality_status} | "
                 f"{case.earliest_observed_deviation or 'none observed'} |" for case in report.cases)
    lines.extend(["", *report.limitations, "", "## Canonical report", ""])
    body = report.model_dump_json(by_alias=True, indent=2)
    fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", body)), default=3))
    lines.extend([fence + "json", body, fence, ""])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate explicit versioned synthetic Gold without network model calls.")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--work-dir", help="Local scratch parent; never cleaned automatically.")
    args = parser.parse_args(argv)
    report = run_gold(args.gold, work_dir=args.work_dir)
    print(report.model_dump_json(by_alias=True, indent=2) if args.format == "json" else render_markdown(report))
    return 0 if report.status == "PASS" else 2 if report.status == "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
