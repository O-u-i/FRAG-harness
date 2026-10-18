"""Complete-evidence synthetic policy; no actual financial advice or provider."""
import json
import pytest

from test_recommendation_workflow import workflow_fixture, assert_isolated, PASSED
from test_required_evidence import tools as fc_tools

from frag_api.services.recommendation_workflow import SyntheticRecommendationWorkflow
from frag_api.schemas.native import PlanConfirmationInput, SearchInput, ReadInput, CompleteInput, SourceProfile, FcInput
from frag_api.schemas.workflow import EvidenceReference


def complete_plan_context(case):
    app, context, _, _ = case
    tools = app.state.tools
    reference = context.evidence[0]
    tools.confirm_plan(PlanConfirmationInput(runId=reference.run_id, evidenceId=reference.required_evidence_ids[0], confirmed=True))
    found = tools.search(SearchInput(query='apples'))
    tools.complete(CompleteInput(runId=found['runId']))
    pack = tools.read(ReadInput(searchRunId=found['runId'], evidenceIds=[found['evidence'][0]['evidenceId']], requireCompletePlan=True))
    tools.complete(CompleteInput(runId=pack['runId']))
    run = tools.repository.get(pack['runId'])
    plan = EvidenceReference(runId=run.id, resultDigest=run.result_digest, requiredEvidenceIds=tuple(pack['requiredEvidenceIds']))
    return context.model_copy(update={'evidence': (plan,), 'plan_evidence': plan, 'plan_revision': pack['evidence'][0]['planRevision']})


def synthetic_economic_context(case):
    context = complete_plan_context(case)
    app, _, _, source = case
    (source.parent / 'economic.md').write_bytes(b'# Synthetic economic fixture\nStockscenario: cash 1000 CNY; debt 200 CNY; obligation 300 CNY due 2026-11-01.\n')
    tools = app.state.tools
    tools.index('kb').build()
    found = tools.search(SearchInput(query='stockscenario'))
    tools.complete(CompleteInput(runId=found['runId']))
    pack = tools.read(ReadInput(searchRunId=found['runId'], evidenceIds=[found['evidence'][0]['evidenceId']]))
    tools.complete(CompleteInput(runId=pack['runId']))
    run = tools.repository.get(pack['runId'])
    economic = EvidenceReference(runId=run.id, resultDigest=run.result_digest, requiredEvidenceIds=(pack['evidence'][0]['evidenceId'],))
    return context.model_copy(update={'evidence': (*context.evidence, economic), 'economic_evidence': economic, 'missing_economic_facts': ()})


def fc_economic_context(case, fc_case, missing=()):
    context = complete_plan_context(case)
    tools = case[0].state.tools
    tools.fc = fc_case[0].fc
    tools.repository.save_profile(SourceProfile(id='finance-core', kind='fc', approved=True))
    record_id = 'economic-evidence:2026-08-31:2026-09-30'
    report = {'schemaVersion': 1, 'calculationVersion': 'economic-evidence-v1', 'asOf': '2026-08-31', 'through': '2026-09-30',
        'revision': 'e' * 64, 'balanceBasis': 'gross-registered-accounts',
        'coverage': {'cashStocks': 'cash_stocks' not in missing, 'liabilityBalances': 'liability_balances' not in missing,
            'datedObligations': 'dated_obligations' not in missing, 'externalCompleteness': 'unknown',
            'currenciesCombined': False, 'personalAvailabilityAssessed': False}, 'missingFacts': list(missing)}
    fc_case[1][record_id] = {'text': 'Deterministic economic evidence. Synthetic official-reader boundary.\n' + json.dumps(report), 'revision': report['revision']}
    pack = tools.fc_read(FcInput(operation='read', workspaceId='sandbox', recordIds=[record_id]))
    tools.complete(CompleteInput(runId=pack['runId']))
    run = tools.repository.get(pack['runId'])
    economic = EvidenceReference(runId=run.id, resultDigest=run.result_digest, requiredEvidenceIds=tuple(pack['requiredEvidenceIds']))
    return context.model_copy(update={'evidence': (*context.evidence, economic), 'economic_evidence': economic, 'missing_economic_facts': ()})


def test_slice_b_cannot_treat_a_plan_digest_and_search_excerpt_as_a_confirmed_plan(workflow_fixture):
    app, context, private, _ = workflow_fixture
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.checked_bytes is None and outcome.reason == 'PLAN_MISSING'
    assert_isolated(workflow_fixture, outcome)


def test_slice_b_refuses_missing_stocks_liabilities_and_obligation_dates_even_with_a_whole_plan(workflow_fixture):
    app, _, private, _ = workflow_fixture
    context = complete_plan_context(workflow_fixture)
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.checked_bytes is None and outcome.reason == 'FINANCIAL_FOUNDATION_MISSING'
    assert_isolated(workflow_fixture, outcome)


def test_complete_confirmed_plan_and_fc_economic_evidence_release_exact_checked_bytes_only(workflow_fixture, fc_tools):
    app, _, private, _ = workflow_fixture
    context = fc_economic_context(workflow_fixture, fc_tools)
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.checked_bytes == private.body
    assert outcome.receipt.rule_version == 'recommendation-complete-evidence-v2'
    assert_isolated(workflow_fixture, outcome)


def test_local_markdown_assertions_cannot_substitute_for_fc_owned_financial_evidence(workflow_fixture):
    app, _, private, _ = workflow_fixture
    context = synthetic_economic_context(workflow_fixture)
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.checked_bytes is None and outcome.reason == 'FINANCIAL_FOUNDATION_MISSING'
    assert_isolated(workflow_fixture, outcome)


@pytest.mark.parametrize('missing', ['cash_stocks', 'liability_balances', 'dated_obligations'])
def test_fc_report_gap_cannot_be_overridden_by_context_assertions(workflow_fixture, fc_tools, missing):
    app, _, private, _ = workflow_fixture
    context = fc_economic_context(workflow_fixture, fc_tools, (missing,))
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    def forbidden(*_):
        pytest.fail('A report with a missing critical fact reached the checker')
    outcome = gate.check_and_release(private, context, checker=forbidden, current_context=lambda: context)
    assert outcome.reason == 'FINANCIAL_FOUNDATION_MISSING' and outcome.checked_bytes is None
    assert_isolated(workflow_fixture, outcome)


@pytest.mark.parametrize('missing', ['cash_stocks', 'liability_balances', 'dated_obligations'])
def test_each_missing_critical_economic_fact_refuses_before_checker(workflow_fixture, missing):
    app, _, private, _ = workflow_fixture
    context = synthetic_economic_context(workflow_fixture).model_copy(update={'missing_economic_facts': (missing,)})
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    def forbidden(*_):
        pytest.fail('Missing economic facts reached checker')
    outcome = gate.check_and_release(private, context, checker=forbidden, current_context=lambda: context)
    assert outcome.reason == 'FINANCIAL_FOUNDATION_MISSING' and outcome.checked_bytes is None
    assert_isolated(workflow_fixture, outcome)


def test_whole_monthly_flows_cannot_attest_stocks_or_dated_obligations(workflow_fixture, fc_tools):
    app, _, private, _ = workflow_fixture
    context = complete_plan_context(workflow_fixture)
    tools = app.state.tools
    tools.fc = fc_tools[0].fc  # Synthetic external FC boundary, no financial runtime import.
    tools.repository.save_profile(SourceProfile(id='finance-core', kind='fc', approved=True))
    pack = tools.fc_read(FcInput(operation='read', workspaceId='sandbox', recordIds=['monthly-review:2025-03']))
    tools.complete(CompleteInput(runId=pack['runId']))
    run = tools.repository.get(pack['runId'])
    economic = EvidenceReference(runId=run.id, resultDigest=run.result_digest, requiredEvidenceIds=tuple(pack['requiredEvidenceIds']))
    context = context.model_copy(update={'evidence': (*context.evidence, economic), 'economic_evidence': economic, 'missing_economic_facts': ()})
    gate = SyntheticRecommendationWorkflow(app.state.workflows, tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.reason == 'FINANCIAL_FOUNDATION_MISSING' and outcome.checked_bytes is None
    assert_isolated(workflow_fixture, outcome)


@pytest.mark.parametrize('change,reason', [('revision', 'REQUIRED_EVIDENCE_INCOMPLETE'), ('source', 'EVIDENCE_STALE'), ('removal', 'PLAN_MISSING')])
def test_plan_revision_source_and_selected_reference_are_required(workflow_fixture, change, reason):
    app, _, private, source = workflow_fixture
    context = synthetic_economic_context(workflow_fixture)
    if change == 'revision':
        context = context.model_copy(update={'plan_revision': '0' * 64})
    elif change == 'source':
        source.write_bytes(b'# Changed plan\nDifferent synthetic constraints.\n')
    else:
        context = context.model_copy(update={'evidence': (context.economic_evidence,)})
    gate = SyntheticRecommendationWorkflow(app.state.workflows, app.state.tools, enabled=True, require_complete_evidence=True)
    outcome = gate.check_and_release(private, context, checker=lambda *_: PASSED, current_context=lambda: context)
    assert outcome.reason == reason and outcome.checked_bytes is None
    assert_isolated(workflow_fixture, outcome)
