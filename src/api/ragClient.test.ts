import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RagPreview, RagRun } from '../../shared/contracts/rag';
import { ApiRequestError } from './apiRequestError';
import {
  evaluateRag, fetchRagStatus, previewRag, rebuildRagIndex, runRag, runRagInference, searchRag,
} from './ragClient';

const dataset = { datasetId: 'synthetic-risk-review-v1' } as const;
const fingerprint = 'a'.repeat(64);
const revision = 'b'.repeat(64);
const chunk = {
  rank: 1, bm25Score: -0.5, chunkId: 'rag-synthetic-risk-review-v1-c002',
  parentId: 'rag-synthetic-risk-review-v1-parent-002', evidenceId: null,
  documentId: 'rag-synthetic-risk-review-v1', sourceId: 'synthetic-risk-review-source-v1',
  locatorId: 'section-2', locatorLabel: 'Regulatory Risk', excerpt: 'Regulatory restrictions increased.',
};
const previewChunk = { ...chunk, evidenceId: chunk.parentId };
const status = {
  ...dataset, schemaVersion: 2, chunkStrategyVersion: 'markdown-hierarchy-v2', state: 'ready',
  documentCount: 1, chunkCount: 3, indexRevision: revision, sourceHash: 'c'.repeat(64),
} as const;
const request = { ...dataset, query: 'What regulatory risks are mentioned?', topK: 3 };
const preview: RagPreview = {
  ...request, indexRevision: revision, retrievalResults: [previewChunk],
  candidateEvidence: [{
    chunkId: chunk.parentId, documentId: chunk.documentId, sourceId: chunk.sourceId,
    locatorId: chunk.locatorId, locatorLabel: chunk.locatorLabel, text: '# Regulatory Risk\nRestrictions increased.',
  }],
  instructions: 'Compress evidence.', input: '{}',
  budget: {
    estimatedInputTokens: 100, inputBudget: 6000, reservedPercent: 25,
    contextOutputLimit: 1500, inferenceOutputLimit: 2000, approximate: true,
  },
  warnings: ['Synthetic only.'], contextFingerprint: fingerprint, approvalToken: 'c'.repeat(48),
};
const run: RagRun = {
  preview,
  compressedContext: {
    evidence: [{ chunkId: chunk.parentId, summary: 'Restrictions increased.', preservedFacts: ['Restrictions increased.'], uncertainty: [] }],
    missingInformation: [],
  },
  result: {
    answer: 'Restrictions increased.', claims: [{ text: 'Restrictions increased.', chunkIds: [chunk.parentId] }],
    missingInformation: [], disclaimer: 'Synthetic only.',
  },
  contextStage: { provider: 'fake', model: 'fake-context-v1', usage: { inputTokens: 10, outputTokens: 8 } },
  inferenceStage: { provider: 'fake', model: 'fake-inference-v1', usage: { inputTokens: 8, outputTokens: 6 } },
};
const context = { preview, compressedContext: run.compressedContext, contextStage: run.contextStage,
  inferencePreview: { provider: 'fake', model: 'fake-inference-v1', instructions: 'Answer.', input: '{}',
    maxOutputTokens: 2000, inferenceFingerprint: 'd'.repeat(64), approvalToken: 'e'.repeat(48) } };

afterEach(() => vi.unstubAllGlobals());

describe('RAG client', () => {
  it('validates status and explicit rebuild', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json(status))
      .mockResolvedValueOnce(Response.json(status));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchRagStatus()).resolves.toEqual(status);
    await expect(rebuildRagIndex(dataset)).resolves.toEqual(status);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/rag/index/rebuild');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual(dataset);
  });

  it('validates search, preview, and approved run', async () => {
    const search = { ...request, indexRevision: revision, results: [chunk] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json(search))
      .mockResolvedValueOnce(Response.json(preview))
      .mockResolvedValueOnce(Response.json(context))
      .mockResolvedValueOnce(Response.json(run));
    vi.stubGlobal('fetch', fetchMock);

    await expect(searchRag(request)).resolves.toEqual(search);
    await expect(previewRag(request)).resolves.toEqual(preview);
    await expect(runRag({ ...request, contextFingerprint: fingerprint, approvalToken: preview.approvalToken, approved: true })).resolves.toEqual(context);
    await expect(runRagInference({ contextFingerprint: fingerprint,
      inferenceFingerprint: context.inferencePreview.inferenceFingerprint,
      approvalToken: context.inferencePreview.approvalToken, approved: true })).resolves.toEqual(run);
  });

  it('validates the deterministic evaluation report', async () => {
    const evaluation = {
      suiteVersion: 'v1', ...dataset,
      cases: [{ id: 'risk', query: request.query, expectedChunkId: chunk.chunkId, actualChunkIds: [chunk.chunkId], expectedRank: 1, passed: true }],
      metrics: { hitAt1: 1, recallAt3: 1, mrrAt3: 1, ndcgAt3: 1 },
      gates: { contextCoverage: 1, citationValidity: 1, expectedCitationCoverage: 1, staleResidualCount: 0 },
      status: 'PASS',
    } as const;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(evaluation)));
    await expect(evaluateRag(dataset)).resolves.toEqual(evaluation);
  });

  it('rejects invalid input before fetch and preserves sanitized API errors', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(searchRag({ ...request, topK: 11 })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      error: { code: 'RAG_INDEX_STALE', message: 'Rebuild required.', issues: [] },
    }, { status: 409 })));
    const error = await searchRag(request).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({ status: 409, code: 'RAG_INDEX_STALE' });
  });
});
