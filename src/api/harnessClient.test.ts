import { afterEach, describe, expect, it, vi } from 'vitest';
import { previewHarness, runHarness, runHarnessInference } from './harnessClient';
import { preparedFixture, reviewTask } from './governanceFixtures';

afterEach(() => vi.unstubAllGlobals());

const selection = { goal: 'Explain the finding', fileSelections: [{
  relativePath: 'evidence.md', locatorIds: ['section-1'], relevanceReason: 'Selected by the reviewer',
}] };

describe('harness client', () => {
  it('rejects missing or mixed evidence sources before a request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(previewHarness({ goal: 'Explain', fileSelections: [] })).rejects.toThrow();
    await expect(previewHarness({ ...selection, pluginSelection: {
      pluginId: 'finance-core', workspaceId: 'one', recordIds: ['record-1'],
    } })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires separate approved Context and Inference requests', async () => {
    const evidence = { evidenceId: 'evidence', documentId: 'doc', sourceId: 'source',
      locatorId: 'section-1', locatorLabel: 'Finding', text: 'Synthetic fact' };
    const preview = { goal: selection.goal, candidateEvidence: [evidence], instructions: 'Compress evidence.', input: '{}',
      budget: { estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25,
        contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true },
      warnings: [], contextFingerprint: 'a'.repeat(64), approvalToken: 'b'.repeat(48) };
    const contextPreview = { ...preview, preparedCall: preparedFixture('context'), sourceBindings: [],
      task: reviewTask, canApprove: true };
    const context = { preview: contextPreview, compressedContext: { evidence: [{evidenceId: 'evidence', summary: 'Synthetic fact',
      preservedFacts: ['Synthetic fact'], uncertainty: []}], missingInformation: [] },
      contextStage: { provider: 'fake', model: 'fake-context-v1', usage: {inputTokens: 1, outputTokens: 1} },
      inferencePreview: { provider: 'fake', model: 'fake-inference-v1', instructions: 'Answer.', input: '{}',
        maxOutputTokens: 2000, inferenceFingerprint: 'c'.repeat(64), approvalToken: 'd'.repeat(48),
        preparedCall: preparedFixture('inference') } };
    const run = { preview: contextPreview, compressedContext: context.compressedContext, contextStage: context.contextStage,
      result: { answer: 'Synthetic fact', claims: [{text: 'Synthetic fact', evidenceIds: ['evidence']}],
        missingInformation: [], disclaimer: 'Review first.' },
      inferenceStage: { provider: 'fake', model: 'fake-inference-v1', usage: {inputTokens: 1, outputTokens: 1} } };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(contextPreview)).mockResolvedValueOnce(Response.json(context))
      .mockResolvedValueOnce(Response.json(run));
    vi.stubGlobal('fetch', fetchMock);
    await expect(previewHarness(selection)).resolves.toEqual(contextPreview);
    await expect(runHarness({ ...selection, contextFingerprint: preview.contextFingerprint,
      approvalToken: preview.approvalToken, approved: true })).resolves.toEqual(context);
    await expect(runHarnessInference({ contextFingerprint: preview.contextFingerprint,
      inferenceFingerprint: context.inferencePreview.inferenceFingerprint,
      approvalToken: context.inferencePreview.approvalToken, approved: true })).resolves.toEqual(run);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      approved: true, approvalToken: preview.approvalToken, contextFingerprint: preview.contextFingerprint,
    });
    expect(fetchMock.mock.calls[2][0]).toBe('/api/harness/inference/run');
  });
});
