import {
  localFileInspectResponseSchema,
  localFileSourceSchema,
  type LocalFileInspectResponse,
  type LocalFileSource,
} from '../../shared/contracts/contextSource';
import { createApiRequestError } from './apiRequestError';

async function request(path: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(path, init);
  if (!response.ok) throw await createApiRequestError(response, `Context Source request failed (${response.status}).`);
  return await response.json() as unknown;
}

export async function fetchLocalFileSources(): Promise<LocalFileSource[]> {
  const payload = await request('/api/context-sources/files', { method: 'GET', headers: { Accept: 'application/json' } });
  return localFileSourceSchema.array().parse(payload);
}

export async function inspectLocalFile(relativePath: string): Promise<LocalFileInspectResponse> {
  const payload = await request('/api/context-sources/files/inspect', {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ relativePath }),
  });
  return localFileInspectResponseSchema.parse(payload);
}
