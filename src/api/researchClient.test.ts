import { afterEach, describe, expect, it, vi } from 'vitest';
import { researchDecisionSchema, researchPreviewSchema } from '../../shared/contracts/research';
import { runReportSchema } from '../../shared/contracts/runtime';
import { ApiRequestError } from './apiRequestError';
import { preparedFixture, reviewTask } from './governanceFixtures';
import { executeResearch, previewResearch } from './researchClient';

const sourceRequest = { goal: 'Review explicitly selected evidence', fileSelections: [{ relativePath: 'selected.md', locatorIds: ['section-1'], relevanceReason: 'Human selected' }] };
const call = preparedFixture('research');
const preview = { runId: 'run-A', sessionId: 'session', stage: 'research' as const, preparedCall: call, fingerprint: call.fingerprint,
  approvalToken: 'fresh-approval-token', canApprove: true, turn: 1, maxTurns: 3 as const, warnings: [], contextFingerprint: null };
const research = { status: 'ready', turns: [], selectedEvidenceIds: [], missingInformation: [], maxTurns: 3, maxToolCalls: 6, configurationHash: 'c'.repeat(64) };
const report = { schemaVersion: 1, session: { id: 'session', title: 'Research', createdAt: 'now' },
  run: { id: 'run-A', sessionId: 'session', parentRunId: null, kind: 'harness', status: 'ready_research', createdAt: 'now', updatedAt: 'now', version: 1, activeCallId: null },
  selection: { goal: sourceRequest.goal, sourceBindings: [], candidateEvidence: [], task: reviewTask, input: sourceRequest },
  requests: [], toolCalls: [], research, context: null, modelOutput: null, reviews: [], revisions: [], consumedTokens: 0, runTokenLimit: 30000,
  structuralValidation: 'NOT_RUN', semanticReview: 'NOT_RUN', limitations: [] };

afterEach(() => vi.unstubAllGlobals());

describe('Research request boundaries', () => {
  it('previews a typed initial selection without executing or previewing another turn', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(preview)); vi.stubGlobal('fetch', fetchMock);
    await expect(previewResearch('harness', sourceRequest)).resolves.toEqual(preview);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runtime/research/preview');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ kind: 'harness', sourceRequest });
  });
  it('requires explicitly selected KB requests and rejects approval fields or FC before fetch', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    await expect(previewResearch('harness', { ...sourceRequest, approvalToken: 'old-token' })).rejects.toThrow();
    await expect(previewResearch('harness', { ...sourceRequest, fileSelections: [], pluginSelection: { pluginId: 'finance-core', workspaceId: 'workspace', recordIds: ['record'] } })).rejects.toThrow('KB evidence');
    await expect(previewResearch('rag', { ...sourceRequest })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('continues only the owning run with the same explicitly supplied source request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(preview)); vi.stubGlobal('fetch', fetchMock);
    await previewResearch('harness', sourceRequest, preview.runId);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runtime/runs/run-A/research/preview');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ sourceRequest });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...preview, runId: 'run-B' })));
    await expect(previewResearch('harness', sourceRequest, preview.runId)).rejects.toThrow('another run');
  });
  it('dispatches exactly one approved request and returns durable state without a fresh approval', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(report)); vi.stubGlobal('fetch', fetchMock);
    await expect(executeResearch(preview.runId, 'harness', sourceRequest, preview)).resolves.toMatchObject({ run: { status: 'ready_research' }, research });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/runtime/runs/run-A/research/execute');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ sourceRequest, fingerprint: call.fingerprint, approvalToken: preview.approvalToken, approved: true });
  });
  it('refuses stale, blocked or mismatched previews before execution', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    await expect(executeResearch('run-B', 'harness', sourceRequest, preview)).rejects.toThrow();
    await expect(executeResearch('run-A', 'harness', sourceRequest, { ...preview, canApprove: false, approvalToken: null })).rejects.toThrow();
    await expect(executeResearch('run-A', 'harness', sourceRequest, { ...preview, fingerprint: 'd'.repeat(64) })).rejects.toThrow();
    await expect(executeResearch('run-A', 'harness', sourceRequest, { ...preview, stage: 'context' })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('validates the returned run identity and rejects persisted executable approvals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...report, run: { ...report.run, id: 'other-run' } })));
    await expect(executeResearch('run-A', 'harness', sourceRequest, preview)).rejects.toThrow('another selection');
    expect(runReportSchema.safeParse({ ...report, research: { ...research, approvalToken: 'durable-secret' } }).success).toBe(false);
    expect(runReportSchema.safeParse({ ...report, research: { ...research, maxTurns: 4 } }).success).toBe(false);
  });
  it('requires the actual stage purpose, request fingerprint and an approvable token', () => {
    expect(researchPreviewSchema.safeParse({ ...preview, preparedCall: preparedFixture('inference') }).success).toBe(false);
    expect(researchPreviewSchema.safeParse({ ...preview, approvalToken: null }).success).toBe(false);
    expect(researchPreviewSchema.safeParse({ ...preview, canApprove: false, approvalToken: null }).success).toBe(true);
  });
  it('preserves sanitized conflicts and never retries', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ error: { code: 'RUNTIME_CONFLICT', message: 'Source selection changed.', issues: [] } }, { status: 409 }));
    vi.stubGlobal('fetch', fetchMock);
    const error = await executeResearch('run-A', 'harness', sourceRequest, preview).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({ code: 'RUNTIME_CONFLICT', status: 409, message: 'Source selection changed.' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('keeps legacy fixed-flow reports readable without inventing a Research trajectory', () => {
    const { research: _research, ...legacy } = report;
    expect(runReportSchema.parse(legacy).research).toBeNull();
  });
  it.each(['action consistency', 'complete unique identifiers', 'bounded decision arrays'] as const)(
    'matches backend decision validation for %s', (group) => {
      const tool = { callId: 'read-1', name: 'kb.read', arguments: {} };
      const finish = { action: 'finish', toolCalls: [], evidenceIds: ['evidence-1'], missingInformation: [] };
      const continuing = { ...finish, action: 'continue', toolCalls: [tool], evidenceIds: [] };
      const maximumEvidence = Array.from({ length: 60 }, (_, index) => `evidence-${index}`);
      const maximumTools = Array.from({ length: 6 }, (_, index) => ({ ...tool, callId: `read-${index}` }));
      const maximumMissing = Array.from({ length: 20 }, (_, index) => `Unknown ${index}`);
      const valid = { 'action consistency': [finish, continuing], 'complete unique identifiers': [finish, continuing],
        'bounded decision arrays': [{ ...finish, evidenceIds: maximumEvidence, missingInformation: maximumMissing }, { ...continuing, toolCalls: maximumTools }] };
      const invalid = {
        'action consistency': [{ ...finish, action: 'continue' }, { ...finish, toolCalls: [tool] }, { ...continuing, evidenceIds: ['evidence-1'] }],
        'complete unique identifiers': [{ ...finish, evidenceIds: ['', 'evidence-1'] }, { ...finish, evidenceIds: ['evidence-1', 'evidence-1'] },
          { ...continuing, toolCalls: [tool, tool] }, { ...continuing, toolCalls: [{ callId: 'read-1', name: 'kb.read' }] }],
        'bounded decision arrays': [{ ...finish, evidenceIds: [...maximumEvidence, 'evidence-61'] }, { ...finish, missingInformation: [...maximumMissing, 'Overflow'] },
          { ...continuing, toolCalls: [...maximumTools, { ...tool, callId: 'read-extra' }] }],
      };
      for (const decision of valid[group]) expect(researchDecisionSchema.safeParse(decision).success).toBe(true);
      for (const decision of invalid[group]) expect(researchDecisionSchema.safeParse(decision).success).toBe(false);
    },
  );
});
