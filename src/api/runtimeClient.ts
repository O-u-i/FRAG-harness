import { z } from 'zod';
import { harnessRequestSchema, type HarnessRequest } from '../../shared/contracts/harness';
import { ragQueryRequestSchema, type RagQueryRequest } from '../../shared/contracts/rag';
import {
  recoveryPreviewSchema, reviewRequestSchema, revisionRequestSchema, runRecordSchema, runReportSchema, sessionCreateSchema,
  sessionRecordSchema, type RecoveryPreview, type ReviewRequest, type RevisionRequest, type RunRecord, type RunReport, type SessionRecord,
} from '../../shared/contracts/runtime';
import { createApiRequestError } from './apiRequestError';

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`/api/runtime${path}`, init);
  if (!response.ok) throw await createApiRequestError(response, `Runtime request failed (${response.status}).`);
  return response;
}
const json = (body: unknown): RequestInit => ({
  method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
const runPath = (runId: string) => `/runs/${encodeURIComponent(z.string().min(1).parse(runId))}`;

export async function fetchSessions(): Promise<SessionRecord[]> {
  return z.array(sessionRecordSchema).parse(await (await request('/sessions')).json());
}
export async function createSession(title: string): Promise<SessionRecord> {
  return sessionRecordSchema.parse(await (await request('/sessions', json(sessionCreateSchema.parse({ title })))).json());
}
export async function fetchRuns(sessionId?: string): Promise<RunRecord[]> {
  const query = sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : '';
  return z.array(runRecordSchema).parse(await (await request(`/runs${query}`)).json());
}
export async function fetchRunReport(runId: string): Promise<RunReport> {
  return runReportSchema.parse(await (await request(runPath(runId))).json());
}
export async function fetchReportJson(runId: string): Promise<RunReport> {
  return runReportSchema.parse(await (await request(`${runPath(runId)}/report.json`)).json());
}
export async function fetchReportMarkdown(runId: string): Promise<string> {
  return (await request(`${runPath(runId)}/report.md`)).text();
}
export async function reviewRun(runId: string, input: ReviewRequest): Promise<RunReport> {
  return runReportSchema.parse(await (await request(`${runPath(runId)}/review`, json(reviewRequestSchema.parse(input)))).json());
}
export async function saveRevision(runId: string, input: RevisionRequest): Promise<RunReport> {
  return runReportSchema.parse(await (await request(`${runPath(runId)}/revisions`, json(revisionRequestSchema.parse(input)))).json());
}
export function parseReselection(kind: 'harness' | 'rag', input: unknown): HarnessRequest | RagQueryRequest {
  return kind === 'harness' ? harnessRequestSchema.parse(input) : ragQueryRequestSchema.parse(input);
}
export async function previewRecovery(runId: string, kind: 'harness' | 'rag', input: unknown, reopen = false): Promise<RecoveryPreview> {
  const sourceRequest = parseReselection(kind, input);
  return recoveryPreviewSchema.parse(await (await request(`${runPath(runId)}/${reopen ? 'reopen' : 'resume/preview'}`, json({ sourceRequest }))).json());
}
