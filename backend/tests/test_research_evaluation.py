"""Trajectory fixtures assert production dispatch, approval, recovery and observed failures."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from frag_api.evaluation import render_markdown, run_gold

GOLD = Path(__file__).resolve().parents[1] / "eval" / "synthetic-research-gold-v1.json"


def suite():
    return json.loads(GOLD.read_text(encoding="utf-8"))


def write_gold(tmp_path, value):
    path = tmp_path / "research-gold.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def check_map(case):
    return {check.id: check for check in case.checks}


def test_research_gold_executes_actual_cli_and_carries_results_under_fresh_approvals(tmp_path, monkeypatch):
    from frag_api.services.cli_executor import ControlledCLI
    calls = []
    original = ControlledCLI.execute
    def execute(self, payload):
        calls.append((self.definition, payload))
        return original(self, payload)
    monkeypatch.setattr(ControlledCLI, "execute", execute)
    monkeypatch.setenv("FRAG_RESEARCH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("FRAG_CONTEXT_LLM_PROVIDER", "openai")
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "PASS", report.model_dump_json(indent=2)
    assert report.trajectory_status == "PASS" and report.semantic_review_status == "UNDETERMINED"
    assert len(report.cases) == 5 and len(calls) == 5
    assert all(definition.name == "kb.read.cli" for definition, _ in calls)
    assert sum(len(case.trace["researchRequests"]) for case in report.cases) == 13
    for case in report.cases:
        assert case.host_enforcement_status == "PASS" and case.model_quality_status == "PASS"
        assert case.causal_attribution == "UNDETERMINED" and case.unknown_causes
        requests = case.trace["researchRequests"]
        assert all(request["provider"] == "fake" and request["purpose"] == "research" for request in requests)
        assert check_map(case)["research.approval_gate"].status == "PASS"
        assert case.trace["researchReport"]["modelOutput"] is None
        assert all(item["status"] != "dispatching" for item in case.trace["researchReport"]["requests"])
    serialized = report.model_dump_json(by_alias=True)
    assert "approvalToken" not in serialized and "Authorization" not in serialized and "apiKey" not in serialized


@pytest.mark.parametrize("change", ["empty", "duplicate", "cross-duplicate", "too-many-turns", "restart", "statuses"])
def test_invalid_research_gold_stops_before_creating_workspace(tmp_path, change):
    value = suite()
    if change == "empty":
        value["researchCases"] = []
    elif change == "duplicate":
        value["researchCases"].append(copy.deepcopy(value["researchCases"][0]))
    elif change == "cross-duplicate":
        fixed = json.loads((GOLD.parent / "synthetic-gold-v1.json").read_text(encoding="utf-8"))["cases"][0]
        fixed["id"] = value["researchCases"][0]["id"]
        value["cases"] = [fixed]
    elif change == "too-many-turns":
        value["researchCases"][0]["steps"] *= 2
    elif change == "restart":
        value["researchCases"][0]["restartAfterTurn"] = 2
    else:
        value["researchCases"][0]["expectedToolStatuses"] = ["completed", "failed"]
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "ERROR" and report.counts["ERROR"] == 1
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("action,count", [("unknown-tool", 1), ("scope-escape", 1),
                                          ("malformed-call", 1), ("duplicate-call", 2)])
def test_bad_proposals_are_model_failures_but_correct_host_rejections(tmp_path, monkeypatch, action, count):
    from frag_api.services.cli_executor import ControlledCLI
    monkeypatch.setattr(ControlledCLI, "execute", lambda *_: pytest.fail("Rejected proposal started a CLI process"))
    value = suite()
    value["researchCases"] = [{"id": action, "query": "synthetic export approval", "steps": [{"action": action, "count": count}],
                               "expectedStatus": "error", "expectedToolNames": []}]
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    case = report.cases[0]
    assert report.status == "FAIL", report.model_dump_json(indent=2)
    assert case.host_enforcement_status == "PASS" and case.model_quality_status == "FAIL"
    assert check_map(case)["research.termination"].status == "PASS"
    assert case.trace["researchReport"]["toolCalls"] == []
    assert case.causal_attribution == "UNDETERMINED" and case.unknown_causes


def test_three_continuations_exhaust_without_a_fourth_model_request(tmp_path):
    value = suite()
    value["researchCases"] = [{"id": "turn-limit", "query": "synthetic export approval", "steps": [{"action": "read"}] * 3,
                               "expectedStatus": "exhausted", "expectedToolNames": ["kb.read"] * 3}]
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "PASS", report.model_dump_json(indent=2)
    case = report.cases[0]
    assert len(case.trace["researchRequests"]) == 3
    assert check_map(case)["research.limits"].status == "PASS"
    assert case.trace["researchReport"]["modelOutput"] is None


def test_restart_and_sanitized_failure_are_observations_not_implicit_retries(tmp_path):
    value = suite()
    value["researchCases"] = value["researchCases"][-2:]
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "PASS", report.model_dump_json(indent=2)
    restart, failure = report.cases
    assert check_map(restart)["research.restart"].status == "PASS"
    assert len(restart.trace["researchRequests"]) == 2
    tools = failure.trace["researchReport"]["toolCalls"]
    assert tools[0]["status"] == "failed" and tools[0]["errorCode"] == "TOOL_TIMEOUT"
    assert tools[1]["status"] == "completed" and tools[0]["callId"] != tools[1]["callId"]
    assert check_map(failure)["research.result_history.1"].status == "PASS"


def test_scorer_exception_is_error_with_no_sensitive_exception_text(tmp_path, monkeypatch):
    import frag_api.research_evaluation as research_eval
    def broken(*_):
        raise RuntimeError("password=synthetic-private")
    monkeypatch.setattr(research_eval, "score_trajectory", broken)
    value = suite()
    value["researchCases"] = value["researchCases"][:1]
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    assert report.status == "ERROR" and report.counts["ERROR"] == 1
    assert "synthetic-private" not in report.model_dump_json()
    assert check_map(report.cases[0])["research.runner_error"].status == "ERROR"


def test_research_markdown_preserves_the_canonical_report(tmp_path):
    report = run_gold(GOLD, work_dir=tmp_path)
    assert report.status == "PASS", report.model_dump_json(indent=2)
    body = render_markdown(report).split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    assert json.loads(body) == report.model_dump(mode="json", by_alias=True)
    assert report.trajectory_status == "PASS" and report.semantic_review_status == "UNDETERMINED"


def test_actual_research_evaluation_cli_prints_a_structured_report(tmp_path):
    result = subprocess.run([sys.executable, "-m", "frag_api.evaluation", "--gold", str(GOLD),
        "--work-dir", str(tmp_path / "work")], cwd=GOLD.parents[1], capture_output=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["trajectoryStatus"] == "PASS" and report["semanticReviewStatus"] == "UNDETERMINED"
    assert result.stderr == ""


def test_observed_context_loss_and_later_extra_errors_remain_separate_from_unknown_causes(tmp_path):
    value = json.loads((GOLD.parent / "synthetic-gold-v1.json").read_text(encoding="utf-8"))
    value["cases"] = value["cases"][:1]
    case = value["cases"][0]
    case["sampleContext"] = {"evidence": [{"evidenceId": evidence_id, "summary": "Datasets may be exported.",
        "preservedFacts": [], "uncertainty": []} for evidence_id in case["expectedEvidenceIds"]], "missingInformation": []}
    case["sampleAnswer"] = {"answer": "Personal datasets may be exported. Approval is optional.",
        "claims": [{"text": "Personal datasets may be exported.", "evidenceIds": [case["expectedEvidenceIds"][0]]}],
        "missingInformation": [], "disclaimer": "Scripted synthetic deviation."}
    report = run_gold(write_gold(tmp_path, value), work_dir=tmp_path / "work")
    observed = report.cases[0]
    assert observed.status == "FAIL" and observed.host_enforcement_status == "PASS"
    assert observed.earliest_observed_deviation == "context"
    assert "inference.fact.synthetic-only" in observed.secondary_observed_failures
    assert "inference.fact.approval" in observed.secondary_observed_failures
    assert check_map(observed)["citation.identifiers"].status == "PASS"
    assert observed.causal_attribution == "UNDETERMINED" and observed.unknown_causes
