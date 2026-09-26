import { afterEach, describe, expect, it, vi } from 'vitest';
import { previewHarness, runHarness } from './harnessClient';

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

  it('sends an explicit one-time approval token to Run', async () => {
    const evidence = { chunkId: 'chunk', documentId: 'doc', sourceId: 'source',
      locatorId: 'section-1', locatorLabel: 'Finding', text: 'Synthetic fact' };
    const preview = { goal: selection.goal, candidateEvidence: [evidence],
      budget: { estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25,
        contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true },
      warnings: [], contextFingerprint: 'a'.repeat(64), approvalToken: 'b'.repeat(48) };
    const run = { preview, compressedContext: { evidence: [{chunkId: 'chunk', summary: 'Synthetic fact',
      preservedFacts: ['Synthetic fact'], uncertainty: []}], missingInformation: [] },
      result: { answer: 'Synthetic fact', claims: [{text: 'Synthetic fact', chunkIds: ['chunk']}],
        missingInformation: [], disclaimer: 'Review first.' },
      contextStage: { provider: 'fake', model: 'fake-context-v1', usage: {inputTokens: 1, outputTokens: 1} },
      inferenceStage: { provider: 'fake', model: 'fake-inference-v1', usage: {inputTokens: 1, outputTokens: 1} } };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(preview)).mockResolvedValueOnce(Response.json(run));
    vi.stubGlobal('fetch', fetchMock);
    await expect(previewHarness(selection)).resolves.toEqual(preview);
    await expect(runHarness({ ...selection, contextFingerprint: preview.contextFingerprint,
      approvalToken: preview.approvalToken, approved: true })).resolves.toEqual(run);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
      approved: true, approvalToken: preview.approvalToken, contextFingerprint: preview.contextFingerprint,
    });
  });
});
