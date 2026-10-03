import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { RecoveryPreview, RunReport } from '../../../shared/contracts/runtime';
import { preparedFixture, reviewTask } from '../../api/governanceFixtures';
import { RunRecoveryPanel } from './RunRecoveryPanel';

const selection = (name: string) => ({ goal: `Review source ${name}`, fileSelections: [{relativePath: `${name}.md`, locatorIds: ['section-1'], relevanceReason: 'Human selected'}] });
function report(id: string): RunReport {
  return { schemaVersion: 1, session: {id: 'session', title: 'Synthetic', createdAt: 'now'}, run: {id, sessionId: 'session', parentRunId: null,
    kind: 'harness', status: 'ready_context', createdAt: 'now', updatedAt: 'now', version: 1, activeCallId: null},
    selection: {goal: selection(id).goal, sourceBindings: [], candidateEvidence: [], task: reviewTask, input: selection(id)},
    requests: [], context: null, modelOutput: null, reviews: [], revisions: [], consumedTokens: 0, runTokenLimit: 30000,
    structuralValidation: 'NOT_RUN', semanticReview: 'NOT_RUN', limitations: [] };
}
const recovery: RecoveryPreview = {runId: 'A', kind: 'harness', stage: 'context', contextFingerprint: 'a'.repeat(64), preview: {
  goal: 'Review source A', candidateEvidence: [], budget: {estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25, contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true},
  instructions: 'Compress', input: '{}', warnings: [], contextFingerprint: 'a'.repeat(64), approvalToken: 'private-token-A',
  preparedCall: preparedFixture('context'), sourceBindings: [], task: reviewTask, canApprove: true, runId: 'A', sessionId: 'session',
}};

describe('recovery selection isolation', () => {
  it('does not hydrate A sources or prepared approval when B is selected', () => {
    const dispatch = vi.fn();
    const markup = renderToStaticMarkup(<RunRecoveryPanel report={report('B')} busy={false}
      continuation={{runId: 'A', preview: recovery, sourceRequest: selection('A')}} onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={dispatch} />);
    expect(markup).toContain('B.md');
    expect(markup).not.toContain('A.md');
    expect(markup).not.toContain('Approve recovered Context request');
    expect(markup).not.toContain('private-token-A');
    expect(dispatch).not.toHaveBeenCalled();
  });
  it('hydrates a matching explicit continuation without dispatching it', () => {
    const dispatch = vi.fn();
    const markup = renderToStaticMarkup(<RunRecoveryPanel report={report('A')} busy={false}
      continuation={{runId: 'A', preview: recovery, sourceRequest: selection('A')}} onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={dispatch} />);
    expect(markup).toContain('A.md');
    expect(markup).toContain('Approve recovered Context request');
    expect(dispatch).not.toHaveBeenCalled();
  });
});
