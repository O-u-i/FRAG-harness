import { z } from 'zod';
import {
  memoryCandidateSchema, memoryConflictSchema, memoryPromotionSchema, memoryRecommendationSchema,
  memoryRecordSchema, memoryResolutionSchema, memoryRetirementSchema, memoryRevisionSchema, type MemoryRecord, type MemorySelection,
} from '../../shared/contracts/memory';
import { createApiRequestError } from './apiRequestError';

async function request(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(`/api/memory${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) throw await createApiRequestError(response, `Memory request failed (${response.status}).`);
  return response.json();
}
const recordPath = (id: string) => `/${encodeURIComponent(z.string().min(1).max(64).parse(id))}`;
export async function fetchMemories(): Promise<MemoryRecord[]> {
  return z.array(memoryRecordSchema).parse(await request(''));
}
export async function fetchMemoryVersions(id: string): Promise<MemoryRecord[]> {
  return z.array(memoryRecordSchema).parse(await request(`${recordPath(id)}/versions`));
}
export async function createMemoryCandidate(input: z.input<typeof memoryCandidateSchema>): Promise<MemoryRecord> {
  return memoryRecordSchema.parse(await request('/candidates', memoryCandidateSchema.parse(input)));
}
export async function reviseMemory(id: string, input: z.input<typeof memoryRevisionSchema>): Promise<MemoryRecord> {
  return memoryRecordSchema.parse(await request(`${recordPath(id)}/revisions`, memoryRevisionSchema.parse(input)));
}
export async function promoteMemory(id: string, input: z.input<typeof memoryPromotionSchema>): Promise<MemoryRecord> {
  return memoryRecordSchema.parse(await request(`${recordPath(id)}/promote`, memoryPromotionSchema.parse(input)));
}
export async function retireMemory(id: string, version: number): Promise<MemoryRecord> {
  return memoryRecordSchema.parse(await request(`${recordPath(id)}/retire`, memoryRetirementSchema.parse({ version })));
}
export async function markMemoryConflict(memoryIds: string[]): Promise<MemoryRecord[]> {
  return z.array(memoryRecordSchema).length(2).parse(await request('/conflicts', memoryConflictSchema.parse({ memoryIds })));
}
export async function resolveMemoryConflict(versions: MemorySelection[], note: string): Promise<MemoryRecord[]> {
  return z.array(memoryRecordSchema).length(2).parse(await request('/resolve-conflict', memoryResolutionSchema.parse({
    memoryIds: versions.map((item) => item.memoryId), versions, reviewed: true, note,
  })));
}
export async function recommendMemories(runId: string, query: string): Promise<MemoryRecord[]> {
  return z.array(memoryRecordSchema).max(3).refine((items) => items.every((item) => item.status === 'active' && !item.conflicts.length)
    && new Set(items.map((item) => item.id)).size === items.length, 'Only distinct active memories without known conflicts can be recommended.')
    .parse(await request('/recommend', memoryRecommendationSchema.parse({ runId, query })));
}
