import {
  harnessConfigSchema, harnessPreviewSchema, harnessRequestSchema, harnessRunRequestSchema,
  harnessRunSchema, harnessContextRunSchema, type HarnessConfig, type HarnessPreview, type HarnessRequest,
  type HarnessRun, type HarnessRunRequest, type HarnessContextRun,
} from '../../shared/contracts/harness';
import { inferenceRunRequestSchema, type InferenceRunRequest } from '../../shared/contracts/rag';
import { createApiRequestError } from './apiRequestError';

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, init);
  if (!response.ok) throw await createApiRequestError(response, `Harness request failed (${response.status}).`);
  return await response.json() as unknown;
}

export async function fetchHarnessConfig(): Promise<HarnessConfig> {
  return harnessConfigSchema.parse(await request('/api/harness/config'));
}

export async function previewHarness(input: HarnessRequest): Promise<HarnessPreview> {
  return harnessPreviewSchema.parse(await request('/api/harness/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(harnessRequestSchema.parse(input)),
  }));
}

export async function runHarness(input: HarnessRunRequest): Promise<HarnessContextRun> {
  return harnessContextRunSchema.parse(await request('/api/harness/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(harnessRunRequestSchema.parse(input)),
  }));
}

export async function runHarnessInference(input: InferenceRunRequest): Promise<HarnessRun> {
  return harnessRunSchema.parse(await request('/api/harness/inference/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(inferenceRunRequestSchema.parse(input)),
  }));
}
