import { z } from 'zod';
import { researchPreviewSchema, type ResearchPreview } from '../../shared/contracts/research';
import { runReportSchema, type RunReport } from '../../shared/contracts/runtime';
import { parseReselection } from './runtimeClient';
import { createApiRequestError } from './apiRequestError';

export type ResearchKind = 'harness' | 'rag';
export function parseResearchSelection(kind: ResearchKind, input: unknown) {
  const selection = parseReselection(z.enum(['harness', 'rag']).parse(kind), input);
  if ('pluginSelection' in selection && selection.pluginSelection) throw new Error('Research requires explicitly selected KB evidence.');
  return selection;
}
async function post(path: string, body: unknown): Promise<unknown> {
  const response = await fetch(`/api/runtime${path}`, {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) throw await createApiRequestError(response, `Research request failed (${response.status}).`);
  return response.json();
}
const runPath = (runId: string) => `/runs/${encodeURIComponent(z.string().min(1).parse(runId))}/research`;

export async function previewResearch(kind: ResearchKind, input: unknown, runId?: string): Promise<ResearchPreview> {
  const sourceRequest = parseResearchSelection(kind, input);
  const value = researchPreviewSchema.parse(await post(runId ? `${runPath(runId)}/preview` : '/research/preview',
    runId ? { sourceRequest } : { kind, sourceRequest }));
  if (runId && value.runId !== runId) throw new Error('Research preview belongs to another run.');
  return value;
}
export async function executeResearch(runId: string, kind: ResearchKind, input: unknown, preview: ResearchPreview): Promise<RunReport> {
  const sourceRequest = parseResearchSelection(kind, input);
  const call = researchPreviewSchema.parse(preview);
  if (call.runId !== runId || !call.canApprove || !call.approvalToken) throw new Error('Prepare an approvable request for this run first.');
  const value = runReportSchema.parse(await post(`${runPath(runId)}/execute`, {
    sourceRequest, fingerprint: call.fingerprint, approvalToken: call.approvalToken, approved: true,
  }));
  if (value.run.id !== runId || value.run.kind !== kind || !value.research) throw new Error('Research response belongs to another selection.');
  return value;
}
