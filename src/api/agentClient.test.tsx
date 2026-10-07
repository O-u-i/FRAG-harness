import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { agentViewSchema, type AgentView } from '../../shared/contracts/agents';
import { executionBody } from './agentClient';
import { preparedFixture, reviewTask } from './governanceFixtures';
import { ReviewWorkflow } from '../agents/components/ReviewWorkflow';

function fixture(): AgentView {
  const sessionId = 'a'.repeat(32), runId = 'synthetic-run', time = '2026-10-07T00:00:00Z';
  const preview = { goal: 'Review synthetic evidence', candidateEvidence: [], instructions: 'Compress.', input: '{}',
    budget: { estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25, contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true },
    warnings: [], contextFingerprint: 'b'.repeat(64), approvalToken: 'synthetic-private-approval-' + 'c'.repeat(32),
    preparedCall: preparedFixture('context'), sourceBindings: [], task: reviewTask, canApprove: true, runId, sessionId };
  return agentViewSchema.parse({ session: { sessionId, resource: 'frag:/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', version: 2,
    turns: [{ id: 'native-turn', text: preview.goal, createdAt: time, state: 'running', runId }] },
    report: { schemaVersion: 1, session: { id: sessionId, title: 'Synthetic', createdAt: time },
      run: { id: runId, sessionId, parentRunId: null, kind: 'harness', status: 'ready_context', version: 1, createdAt: time, updatedAt: time, activeCallId: null },
      selection: { goal: preview.goal, sourceBindings: [], candidateEvidence: [], task: reviewTask, input: {} },
      requests: [], context: null, modelOutput: null, reviews: [], revisions: [], consumedTokens: 0, runTokenLimit: 30000,
      structuralValidation: 'NOT_RUN', semanticReview: 'NOT_RUN', limitations: [] },
    preview: { runId, kind: 'harness', stage: 'context', contextFingerprint: preview.contextFingerprint, preview } });
}

describe('native review control boundaries', () => {
  it('rejects controls from a different native session or run before dispatch', () => {
    const value = fixture();
    expect(executionBody(value).runId).toBe(value.report!.run.id);
    expect(() => executionBody({ ...value, report: { ...value.report!, run: { ...value.report!.run, sessionId: 'other' } } })).toThrow();
    expect(() => executionBody({ ...value, preview: { ...value.preview!, runId: 'other' } })).toThrow();
    expect(() => executionBody({ ...value, session: { ...value.session, turns: [{ ...value.session.turns[0], state: 'cancelled' }] } })).toThrow();
  });
  it('shows the exact request with approval disabled until explicit review, without rendering the token', () => {
    const value = fixture();
    const markup = renderToStaticMarkup(<ReviewWorkflow view={value} config={{
      context: { provider: 'fake', model: 'synthetic-context', ready: true },
      inference: { provider: 'fake', model: 'synthetic-inference', ready: true },
    }} onChange={() => undefined} />);
    expect(markup).toContain('Complete request JSON');
    expect(markup).toContain(value.preview!.preview.preparedCall.endpoint);
    expect(markup).toContain('I reviewed this exact request');
    expect(markup).toMatch(/disabled=""[^>]*>Approve context/);
    expect(markup).not.toContain(value.preview!.preview.approvalToken!);
  });
});
