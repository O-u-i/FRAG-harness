import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ResearchPreview } from '../../../shared/contracts/research';
import type { RunReport } from '../../../shared/contracts/runtime';
import { preparedFixture, reviewTask } from '../../api/governanceFixtures';
import { matchingResearchContinuation, ResearchPanel, type ResearchContinuation } from './ResearchPanel';
import { ResearchTrajectoryView } from './ResearchTrajectoryView';

const source = (id: string) => ({ goal: `Review selected source ${id}`, fileSelections: [{ relativePath: `${id}.md`, locatorIds: ['section-1'], relevanceReason: 'Human selected' }] });
function report(id: string): RunReport {
  return { schemaVersion: 1, session: { id: 'session', title: 'Research', createdAt: 'now' }, run: { id, sessionId: 'session', parentRunId: null,
    kind: 'harness', status: 'ready_research', createdAt: 'now', updatedAt: 'now', version: 1, activeCallId: null },
    selection: { goal: source(id).goal, sourceBindings: [], candidateEvidence: [], task: reviewTask, input: source(id) }, requests: [], toolCalls: [],
    research: { status: 'ready', turns: [], selectedEvidenceIds: [], missingInformation: [], maxTurns: 3, maxToolCalls: 6, configurationHash: 'c'.repeat(64) },
    context: null, modelOutput: null, reviews: [], revisions: [], consumedTokens: 0, runTokenLimit: 30000,
    structuralValidation: 'NOT_RUN', semanticReview: 'NOT_RUN', limitations: [] };
}
const call = preparedFixture('research');
const preview: ResearchPreview = { runId: 'A', sessionId: 'session', stage: 'research', preparedCall: call, fingerprint: call.fingerprint,
  approvalToken: 'one-use-not-displayable', canApprove: true, turn: 1, maxTurns: 3, warnings: [], contextFingerprint: null };
const continuation: ResearchContinuation = { runId: 'A', kind: 'harness', preview, sourceRequest: source('A') };

describe('Research UI selection and checkpoint boundaries', () => {
  it('does not hydrate another run source or approval', () => {
    const dispatch = vi.fn();
    const markup = renderToStaticMarkup(<ResearchPanel report={report('B')} busy={false} continuation={continuation}
      onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={dispatch} />);
    expect(markup).toContain('B.md'); expect(markup).not.toContain('A.md');
    expect(markup).not.toContain('Approve displayed Research request'); expect(markup).not.toContain(preview.approvalToken!);
    expect(dispatch).not.toHaveBeenCalled();
    expect(matchingResearchContinuation(report('B'), continuation)).toBeUndefined();
    expect(matchingResearchContinuation(report('A'), { ...continuation, kind: 'rag' })).toBeUndefined();
    expect(matchingResearchContinuation(report('A'), { ...continuation, preview: { ...preview, sessionId: 'other-session' } })).toBeUndefined();
  });
  it('displays an exact matching preview without dispatching or exposing the approval token', () => {
    const dispatch = vi.fn(); const prepare = vi.fn();
    const markup = renderToStaticMarkup(<ResearchPanel report={report('A')} busy={false} continuation={continuation}
      onInvalidate={vi.fn()} onPrepare={prepare} onDispatch={dispatch} />);
    expect(markup).toContain('Research turn 1 / 3'); expect(markup).toContain('Complete request JSON');
    expect(markup).toContain('Approve displayed Research request'); expect(markup).not.toContain(preview.approvalToken!);
    expect(dispatch).not.toHaveBeenCalled(); expect(prepare).not.toHaveBeenCalled();
  });
  it('blocks unknown outcomes and exhausted loops from automatically continuing', () => {
    for (const state of ['outcome_unknown', 'exhausted'] as const) {
      const current = report('A'); current.research!.status = state;
      if (state === 'outcome_unknown') current.run.status = state;
      const markup = renderToStaticMarkup(<ResearchPanel report={current} busy={false}
        onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={vi.fn()} />);
      expect(markup).toContain('checkpoint cannot continue');
      expect(markup).toContain('disabled="">Preview next Research stage');
      expect(markup).toContain('Preview linked Research run');
      expect(markup).not.toContain('disabled="">Preview linked Research run');
    }
  });
  it('offers explicit opt-in before any saved run exists and keeps FC outside Research', () => {
    const prepare = vi.fn();
    const markup = renderToStaticMarkup(<ResearchPanel busy={false} onInvalidate={vi.fn()} onPrepare={prepare} onDispatch={vi.fn()} />);
    expect(markup).toContain('Start Research'); expect(markup).toContain('Research source selection JSON');
    expect(markup).toContain('Finance Core stays on the fixed workflow');
    expect(markup).toContain('disabled="">Preview initial Research request'); expect(prepare).not.toHaveBeenCalled();
  });
  it('compares selected RAG file and locators before offering saved-scope memories', () => {
    const selected = { datasetId: 'selected-local-v1', query: 'Review uncertainty', topK: 3,
      sourceSelection: { relativePath: 'a.md', locatorIds: ['section-1'], relevanceReason: 'Human selected this source.' } };
    const current = report('A'); current.run.kind = 'rag'; current.selection.input = selected;
    for (const sourceSelection of [
      { ...selected.sourceSelection, relativePath: 'b.md' },
      { ...selected.sourceSelection, locatorIds: ['section-2'] },
    ]) {
      const markup = renderToStaticMarkup(<ResearchPanel report={current} busy={false}
        continuation={{ ...continuation, kind: 'rag', sourceRequest: { ...selected, sourceSelection } }}
        onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={vi.fn()} />);
      expect(markup).toContain('disabled="">Recommend reviewed memories');
    }
    const markup = renderToStaticMarkup(<ResearchPanel report={current} busy={false}
      continuation={{ ...continuation, kind: 'rag', sourceRequest: { ...selected, sourceSelection: {
        ...selected.sourceSelection, relevanceReason: 'A more detailed reason for the same source.',
      } } }} onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={vi.fn()} />);
    expect(markup).toContain('Recommend reviewed memories');
    expect(markup).not.toContain('disabled="">Recommend reviewed memories');
  });
  it('keeps the server-serialized synthetic RAG selection usable after restoring history', () => {
    const current = report('A'); current.run.kind = 'rag';
    current.selection.input = { datasetId: 'synthetic-risk-review-v1', sourceSelection: null,
      query: 'Review synthetic uncertainty', topK: 3, selectedMemory: [], task: reviewTask,
      sessionId: null, parentRunId: null };
    const markup = renderToStaticMarkup(<ResearchPanel report={current} busy={false}
      onInvalidate={vi.fn()} onPrepare={vi.fn()} onDispatch={vi.fn()} />);
    expect(markup).toContain('Recommend reviewed memories');
    expect(markup).not.toContain('disabled="">Recommend reviewed memories');
    expect(markup).toContain('Preview next Research stage');
    expect(markup).not.toContain('disabled="">Preview next Research stage');
  });
  it('renders persisted decisions, selected evidence and unknown gaps separately from final answers', () => {
    const current = report('A'); current.research = { ...current.research!, status: 'awaiting_context', selectedEvidenceIds: ['evidence-1'],
      missingInformation: ['Duration remains unknown.'], turns: [{ number: 1, attemptId: 'attempt-1', status: 'completed', errorCode: null,
        decision: { action: 'finish', toolCalls: [], evidenceIds: ['evidence-1'], missingInformation: ['Duration remains unknown.'] } }] };
    const markup = renderToStaticMarkup(<ResearchTrajectoryView report={current} />);
    expect(markup).toContain('1 / 3 model turns'); expect(markup).toContain('0 / 6 tools');
    expect(markup).toContain('Context evidence: evidence-1'); expect(markup).toContain('Duration remains unknown.');
    expect(markup).toContain('final answer still requires Context, Inference and human review');
  });
});
