import { afterEach, describe, expect, it, vi } from 'vitest';
import { recoveryPreviewSchema, runReportSchema } from '../../shared/contracts/runtime';
import { ApiRequestError } from './apiRequestError';
import { preparedFixture, reviewTask } from './governanceFixtures';
import { createSession, fetchRuns, fetchSessions, fetchRunReport, fetchReportMarkdown, previewRecovery, reviewRun, saveRevision } from './runtimeClient';

const session = { id: 'session-1', title: 'Synthetic review', createdAt: '2026-10-03T00:00:00Z' };
const run = { id: 'run-1', sessionId: session.id, parentRunId: null, kind: 'harness', status: 'awaiting_review',
  createdAt: session.createdAt, updatedAt: session.createdAt, version: 1, activeCallId: null } as const;
const selection = { goal: 'Review synthetic evidence', fileSelections: [{ relativePath: 'evidence.md',
  locatorIds: ['section-1'], relevanceReason: 'Explicit review selection' }], task: reviewTask, sessionId: session.id };
const answer = { answer: 'Original model answer.', claims: [{ text: 'Synthetic fact.', evidenceIds: ['evidence-1'] }], missingInformation: [], disclaimer: 'Review first.' };
const report = { schemaVersion: 1, session, run,
  selection: { goal: selection.goal, sourceBindings: [], candidateEvidence: [], task: reviewTask, input: selection },
  requests: [{ id: 'attempt-1', stage: 'inference', status: 'completed', preparedCall: preparedFixture('inference'),
    createdAt: session.createdAt, finishedAt: session.createdAt, usage: {inputTokens: 8, outputTokens: 6}, output: answer, errorCode: null, structuralValidation: 'PASS' }],
  context: null, modelOutput: answer, reviews: [], revisions: [], consumedTokens: 14, runTokenLimit: 30000,
  structuralValidation: 'PASS', semanticReview: 'UNDETERMINED', limitations: ['Structural checks do not establish semantic support.'] } as const;
const contextPreview = { goal: selection.goal, candidateEvidence: [], instructions: 'Compress evidence.', input: '{}',
  budget: { estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25, contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true },
  warnings: [], contextFingerprint: 'a'.repeat(64), approvalToken: 'b'.repeat(48),
  preparedCall: preparedFixture('context'), sourceBindings: [], task: reviewTask, canApprove: true, runId: run.id, sessionId: session.id };
const recovery = { runId: run.id, kind: 'harness', stage: 'context', contextFingerprint: 'a'.repeat(64), preview: contextPreview };

afterEach(() => vi.unstubAllGlobals());

describe('runtime client boundaries', () => {
  it('reads session-scoped history without dispatching a model request', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json([session])).mockResolvedValueOnce(Response.json([run])).mockResolvedValueOnce(Response.json(report));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchSessions()).resolves.toEqual([session]);
    await expect(fetchRuns('scope/a')).resolves.toEqual([run]);
    await expect(fetchRunReport(run.id)).resolves.toMatchObject({ structuralValidation: 'PASS', semanticReview: 'UNDETERMINED' });
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/api/runtime/sessions', '/api/runtime/runs?sessionId=scope%2Fa', '/api/runtime/runs/run-1']);
    expect(fetchMock.mock.calls.every((call) => call[1] === undefined)).toBe(true);
  });

  it('requires an explicit valid reselection and only prepares the recovery endpoint', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => Response.json(recovery));
    vi.stubGlobal('fetch', fetchMock);
    await expect(previewRecovery(run.id, 'harness', { ...selection, approvalToken: 'old-token' })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
    await expect(previewRecovery(run.id, 'harness', selection)).resolves.toEqual(recovery);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runtime/runs/run-1/resume/preview');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ sourceRequest: selection });
    await previewRecovery(run.id, 'harness', selection, true);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/runtime/runs/run-1/reopen');
  });

  it('rejects persistent executable approval fields, unknown statuses and mismatched recovery stages', () => {
    expect(runReportSchema.safeParse({ ...report, approvalToken: 'old-token' }).success).toBe(false);
    expect(runReportSchema.safeParse({ ...report, run: { ...run, status: 'automatically_resending' } }).success).toBe(false);
    expect(runReportSchema.safeParse({ ...report, requests: [{ ...report.requests[0], approvalToken: 'old-token' }] }).success).toBe(false);
    expect(recoveryPreviewSchema.safeParse({ ...recovery, stage: 'inference' }).success).toBe(false);
    expect(recoveryPreviewSchema.safeParse({ ...recovery, runId: 'other-run' }).success).toBe(false);
    expect(recoveryPreviewSchema.safeParse({ ...recovery, preview: { ...contextPreview, preparedCall: preparedFixture('inference') } }).success).toBe(false);
  });

  it('stores a separate revision and human review without replacing the model original', async () => {
    const revision = { id: 'revision-1', createdAt: session.createdAt, reviewStatus: 'pending', result: { ...answer, answer: 'Human revision.' }, note: 'Corrected wording.' };
    const fetchMock = vi.fn().mockImplementation(async () => Response.json({ ...report, revisions: [revision], semanticReview: 'NOT_RUN' }));
    vi.stubGlobal('fetch', fetchMock);
    const revised = await saveRevision(run.id, { result: revision.result, note: revision.note });
    expect(revised.modelOutput?.answer).toBe(answer.answer);
    expect(revised.revisions[0].result.answer).toBe('Human revision.');
    await reviewRun(run.id, { target: revision.id, decision: 'paused', checklist: reviewTask, note: 'Evidence support still needs review.' });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({ target: revision.id, decision: 'paused' });
    expect(fetchMock.mock.calls.every((call) => !call[0].includes('/inference/run'))).toBe(true);
  });

  it('validates actions before fetch and preserves a sanitized runtime conflict', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    await expect(createSession('')).rejects.toThrow();
    await expect(reviewRun(run.id, { target: 'model', decision: 'accepted', checklist: { ...reviewTask,
      checklist: [{id: 'duplicate', text: 'One', blocking: true, status: 'met', reviewed: true}, {id: 'duplicate', text: 'Two', blocking: false, status: 'unknown', reviewed: true}] }, note: '' })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: { code: 'RUNTIME_CONFLICT', message: 'Source selection changed.', issues: [] } }, {status: 409})));
    const error = await previewRecovery(run.id, 'harness', selection).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({code: 'RUNTIME_CONFLICT', status: 409, message: 'Source selection changed.'});
  });

  it('fetches Markdown as text only when requested', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('# Saved report\nSemantic review: UNDETERMINED'));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchReportMarkdown(run.id)).resolves.toContain('UNDETERMINED');
    expect(fetchMock).toHaveBeenCalledWith('/api/runtime/runs/run-1/report.md', undefined);
  });
});
