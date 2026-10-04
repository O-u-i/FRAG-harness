import { z } from 'zod';
import {
  ragDatasetRequestSchema,
  ragEvaluationReportSchema,
  ragIndexStatusSchema,
  ragPreviewSchema,
  ragQueryRequestSchema,
  ragRunRequestSchema,
  ragContextRunSchema,
  inferenceRunRequestSchema,
  ragRunSchema,
  ragSearchResponseSchema,
  type RagDatasetRequest,
  type RagEvaluationReport,
  type RagIndexStatus,
  type RagPreview,
  type RagQueryRequest,
  type RagRun,
  type RagContextRun,
  type RagRunRequest,
  type InferenceRunRequest,
  type RagSearchResponse,
} from '../../shared/contracts/rag';
import { createApiRequestError } from './apiRequestError';

const RAG_TIMEOUT_MS = 60_000;

async function request(path: string, init: RequestInit): Promise<unknown> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), RAG_TIMEOUT_MS);
  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    if (!response.ok) throw await createApiRequestError(response, `RAG request failed (${response.status}).`);
    try { return await response.json() as unknown; }
    catch { throw new Error('Backend returned invalid JSON for RAG.'); }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('RAG request timed out.');
    if (error instanceof Error) throw error;
    throw new Error('RAG request failed.');
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

const json = (body: object): RequestInit => ({
  method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function parse<T>(schema: z.ZodType<T>, payload: unknown, label: string): T {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) throw new Error(`Backend returned an invalid RAG ${label}.`);
  return parsed.data;
}

export async function fetchRagStatus(): Promise<RagIndexStatus> {
  return parse(ragIndexStatusSchema, await request('/api/rag/status', {
    method: 'GET', headers: { Accept: 'application/json' },
  }), 'status');
}

export async function rebuildRagIndex(input: RagDatasetRequest): Promise<RagIndexStatus> {
  const body = ragDatasetRequestSchema.parse(input);
  return parse(ragIndexStatusSchema, await request('/api/rag/index/rebuild', json(body)), 'status');
}

export async function searchRag(input: RagQueryRequest): Promise<RagSearchResponse> {
  const body = ragQueryRequestSchema.parse(input);
  return parse(ragSearchResponseSchema, await request('/api/rag/search', json(body)), 'search result');
}

export async function previewRag(input: RagQueryRequest): Promise<RagPreview> {
  const body = ragQueryRequestSchema.parse(input);
  return parse(ragPreviewSchema, await request('/api/rag/preview', json(body)), 'preview');
}

export async function runRag(input: RagRunRequest): Promise<RagContextRun> {
  const body = ragRunRequestSchema.parse(input);
  return parse(ragContextRunSchema, await request('/api/rag/run', json(body)), 'context run');
}

export async function runRagInference(input: InferenceRunRequest): Promise<RagRun> {
  const body = inferenceRunRequestSchema.parse(input);
  return parse(ragRunSchema, await request('/api/rag/inference/run', json(body)), 'inference run');
}

export async function evaluateRag(input: RagDatasetRequest): Promise<RagEvaluationReport> {
  const body = ragDatasetRequestSchema.parse(input);
  return parse(ragEvaluationReportSchema, await request('/api/rag/evaluations/run', json(body)), 'evaluation');
}
