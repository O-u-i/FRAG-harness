import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import frag_api.evaluation as evaluation
from frag_api.evaluation import render_markdown, run_gold

GOLD = Path(__file__).resolve().parents[1] / "eval" / "synthetic-gold-v1.json"


def suite():
    return json.loads(GOLD.read_text(encoding="utf-8"))


def write_gold(tmp_path, value):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def checks(case):
    return {item.id: item for item in case.checks}


def answer_sample(text, evidence_id):
    return {"answer": text, "claims": [{"text": text, "evidenceIds": [evidence_id]}],
            "missingInformation": [], "disclaimer": "Synthetic fixture only."}


def test_versioned_gold_runs_production_fixed_flow_without_network(tmp_path, monkeypatch):
    calls = []
    original = evaluation.ScriptedProvider.execute_prepared

    def execute(self, call):
        calls.append(call)
        return original(self, call)

    monkeypatch.setattr(evaluation.ScriptedProvider, "execute_prepared", execute)
    monkeypatch.setenv("FRAG_CONTEXT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("FRAG_INFERENCE_LLM_PROVIDER", "openai")
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "PASS", report.model_dump_json()
    assert len(report.cases) == 4
    assert report.semantic_review_status == "UNDETERMINED"
    assert report.trajectory_status == "NOT_RUN"
    assert len(calls) == 6
    assert all(call.provider == "fake" and call.max_retries == 0 for call in calls)
    assert [call.purpose for call in calls] == ["context", "inference"] * 3
    assert all(case.host_enforcement_status == "PASS" for case in report.cases)
    assert report.cases[-1].model_quality_status == "NOT_RUN"
    assert "contextRequest" not in report.cases[-1].trace
    serialized = report.model_dump_json(by_alias=True)
    assert "approvalToken" not in serialized and "Authorization" not in serialized


@pytest.mark.parametrize("change", ["hash", "version", "identifier", "duplicate-case", "empty-facts"])
def test_invalid_gold_is_error_before_creating_workspace(tmp_path, change):
    value = suite()
    if change == "hash":
        value["source"]["sha256"] = "0" * 64
    elif change == "version":
        value["schemaVersion"] = 2
    elif change == "identifier":
        value["cases"][0]["expectedChunkIds"] = ["unknown-chunk"]
    elif change == "duplicate-case":
        value["cases"].append(copy.deepcopy(value["cases"][0]))
    else:
        value["cases"][0]["facts"] = []
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "ERROR"
    assert report.counts["ERROR"] == 1
    assert not (tmp_path / "work").exists()


def test_duplicate_json_keys_and_missing_file_are_error(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
    assert run_gold(path, work_dir=tmp_path / "work").status == "ERROR"
    assert run_gold(tmp_path / "missing.json", work_dir=tmp_path / "work").status == "ERROR"


def test_multi_gold_requires_every_required_chunk(tmp_path):
    value = suite()
    value["cases"] = value["cases"][:1]
    value["cases"][0].update({"topK": 1, "mode": "retrieval"})
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    check = checks(report.cases[0])["retrieval.coverage"]
    assert report.status == "FAIL"
    assert check.observed["recallAtK"] == 0.5
    assert len(check.observed["missingIds"]) == 1
    assert report.cases[0].earliest_observed_deviation == "retrieval"


def test_zero_retrieval_is_failure_with_no_model_call_not_a_runner_error(tmp_path, monkeypatch):
    value = suite()
    value["cases"] = value["cases"][:1]
    value["cases"][0]["query"] = "quasar heliosphere"
    def forbidden(*args):
        raise AssertionError("No model call may execute without selected evidence.")
    monkeypatch.setattr(evaluation.ScriptedProvider, "execute_prepared", forbidden)
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "FAIL"
    assert report.counts["ERROR"] == 0
    assert checks(report.cases[0])["context.execution"].status == "NOT_RUN"
    assert report.cases[0].model_quality_status == "NOT_RUN"


def test_context_qualifier_loss_fails_even_when_host_ids_pass(tmp_path):
    value = suite()
    value["cases"] = value["cases"][:1]
    case = value["cases"][0]
    case["sampleContext"] = {"evidence": [
        {"evidenceId": case["expectedEvidenceIds"][0], "summary": "Datasets may be exported.",
         "preservedFacts": [], "uncertainty": []},
        {"evidenceId": case["expectedEvidenceIds"][1], "summary": "Approval is optional.",
         "preservedFacts": [], "uncertainty": []}], "missingInformation": []}
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    result = report.cases[0]
    assert report.status == "FAIL"
    assert result.earliest_observed_deviation == "context"
    assert checks(result)["host.context"].status == "PASS"
    assert checks(result)["context.fact.synthetic-only"].status == "FAIL"
    assert checks(result)["context.fact.approval"].observed["forbiddenFound"]
    assert "inferenceOutput" in result.trace


def test_bad_context_identifier_is_rejected_and_inference_not_run(tmp_path):
    value = suite()
    value["cases"] = value["cases"][:1]
    value["cases"][0]["sampleContext"] = {"evidence": [
        {"evidenceId": "unknown-evidence", "summary": "Only synthetic datasets may be exported.",
         "preservedFacts": [], "uncertainty": []}], "missingInformation": []}
    result = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work").cases[0]
    assert result.status == "FAIL"
    assert checks(result)["context.identifiers"].status == "FAIL"
    assert checks(result)["host.context"].status == "PASS"
    assert checks(result)["inference.execution"].status == "NOT_RUN"
    assert "inferenceRequest" not in result.trace


@pytest.mark.parametrize("text,failed_fact", [
    ("Deletion is enabled. Retention is limited to at most 14 days. The result limit is 8 MiB.", "deletion-disabled"),
    ("Deletion is not enabled. Retention is limited to at least 14 days. The result limit is 8 MiB.", "retention-cap"),
    ("Deletion is not enabled. Retention is limited to at most 14 days. The result limit is 8 MB.", "result-unit"),
])
def test_reversed_negation_constraints_and_units_fail_with_legal_citations(tmp_path, text, failed_fact):
    value = suite()
    value["cases"] = [value["cases"][1]]
    case = value["cases"][0]
    case["sampleAnswer"] = answer_sample(text, case["expectedEvidenceIds"][0])
    result = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work").cases[0]
    assert result.status == "FAIL"
    assert checks(result)[f"inference.fact.{failed_fact}"].status == "FAIL"
    assert checks(result)["citation.identifiers"].status == "PASS"
    assert checks(result)["host.citation"].status == "PASS"
    assert result.earliest_observed_deviation == "inference"


def test_wrong_date_fails_and_unknown_information_is_checked(tmp_path):
    value = suite()
    value["cases"] = [value["cases"][2]]
    case = value["cases"][0]
    case["sampleAnswer"] = answer_sample("The policy became effective on 2026-11-01. The maintenance owner is unknown.",
                                         case["expectedEvidenceIds"][0])
    case["requiredMissingInformation"] = ["maintenance owner identity"]
    result = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work").cases[0]
    assert checks(result)["inference.fact.effective-date"].status == "FAIL"
    assert checks(result)["inference.missing.0"].status == "FAIL"


def test_invalid_citation_has_bad_model_quality_but_good_host_enforcement(tmp_path):
    value = suite()
    value["cases"] = [value["cases"][2]]
    value["cases"][0]["sampleAnswer"] = answer_sample(
        "The policy became effective on 2026-10-01. The maintenance owner is unknown.", "unknown-evidence")
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    result = report.cases[0]
    assert report.status == "FAIL"
    assert result.host_enforcement_status == "PASS"
    assert result.model_quality_status == "FAIL"
    assert checks(result)["citation.identifiers"].status == "FAIL"
    assert checks(result)["host.citation"].status == "PASS"


def test_broken_scorer_is_error_instead_of_pass(tmp_path, monkeypatch):
    def broken(*args):
        raise RuntimeError("synthetic scorer failure")
    monkeypatch.setattr(evaluation, "score_facts", broken)
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "ERROR"
    assert report.counts["ERROR"] == 4
    assert all(checks(case)["runner.error"].status == "ERROR" for case in report.cases)
    assert "synthetic scorer failure" not in report.model_dump_json()


def test_gold_tool_fixture_uses_actual_registered_child_process(tmp_path, monkeypatch):
    from frag_api.services.cli_executor import ControlledCLI
    invocations = []
    original = ControlledCLI.execute
    def execute(self, payload):
        invocations.append((self.definition, payload))
        return original(self, payload)
    monkeypatch.setattr(ControlledCLI, "execute", execute)
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "PASS"
    assert len(invocations) == 1
    definition, payload = invocations[0]
    assert definition.name == "kb.read.cli"
    observations = report.cases[0].trace["tools"]
    assert observations[0]["callId"] == payload["callId"] == observations[0]["result"]["callId"]
    assert observations[0]["result"]["evidence"] == payload["evidence"]
    assert observations[2]["result"]["evidence"] == []
    assert observations[2]["result"]["missingInformation"]
    assert all(check.status == "PASS" for check in report.cases[0].checks if check.category == "tool")


def test_broken_tool_carrier_is_error_not_a_fact_failure(tmp_path, monkeypatch):
    from frag_api.services.cli_executor import ControlledCLI, ToolExecutionError
    def broken(self, payload):
        raise ToolExecutionError("TOOL_TIMEOUT")
    monkeypatch.setattr(ControlledCLI, "execute", broken)
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "ERROR"
    check = checks(report.cases[0])["tool.kb.read.execution"]
    assert check.category == "tool" and check.status == "ERROR"
    assert check.observed["code"] == "TOOL_TIMEOUT"


def test_evidence_fact_loss_is_observed_before_context(tmp_path, monkeypatch):
    original = evaluation.RagService._expanded_evidence
    def truncated(self, *args, **kwargs):
        evidence, mapping = original(self, *args, **kwargs)
        for item in evidence:
            item.text = item.text.replace("Only synthetic datasets may be exported.", "Datasets may be exported.")
        return evidence, mapping
    monkeypatch.setattr(evaluation.RagService, "_expanded_evidence", truncated)
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "FAIL"
    result = report.cases[0]
    assert result.earliest_observed_deviation == "evidence"
    assert checks(result)["evidence.fact.synthetic-only"].status == "FAIL"
    assert checks(result)["context.fact.synthetic-only"].status == "FAIL"


def test_markdown_contains_same_canonical_structured_report(tmp_path):
    report = run_gold(GOLD, work_dir=tmp_path)
    markdown = render_markdown(report)
    payload = markdown.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    assert json.loads(payload) == report.model_dump(mode="json", by_alias=True)
    assert "UNDETERMINED" in markdown and "NOT_RUN" in markdown


@pytest.mark.parametrize("kind,exit_code,status", [("pass", 0, "PASS"), ("fail", 2, "FAIL"), ("error", 1, "ERROR")])
def test_actual_module_cli_has_structured_stdout_and_exit_codes(tmp_path, kind, exit_code, status):
    value = suite()
    if kind == "fail":
        value["cases"][0].update({"topK": 1, "mode": "retrieval"})
    elif kind == "error":
        value["source"]["sha256"] = "0" * 64
    path = write_gold(tmp_path, value)
    environment = {key: val for key, val in os.environ.items() if key != "OPENAI_API_KEY" and not key.startswith("FRAG_")}
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([sys.executable, "-m", "frag_api.evaluation", "--gold", str(path),
                             "--work-dir", str(tmp_path / "work")], cwd=GOLD.parents[1], env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)
    assert result.returncode == exit_code, result.stderr
    assert json.loads(result.stdout)["status"] == status
    assert result.stderr == ""
