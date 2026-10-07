import { agentSessionSchema, agentViewSchema, type AgentView } from '../../shared/contracts/agents';
import { createApiRequestError } from './apiRequestError';
import { parseReselection } from './runtimeClient';
import type { HarnessRequest } from '../../shared/contracts/harness';
import type { RagQueryRequest } from '../../shared/contracts/rag';

async function request(path: string, body?: unknown) {
  const response = await fetch(`/api/agents/sessions${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) throw await createApiRequestError(response, 'FRAG review could not complete this action.');
  return response.json() as Promise<unknown>;
}
const path = (id: string) => `/${agentSessionSchema.shape.sessionId.parse(id)}`;
export async function fetchAgentSessions() { return agentSessionSchema.array().parse(await request('')); }
export async function fetchAgentView(id: string) { return agentViewSchema.parse(await request(path(id))); }
export async function prepareAgent(view: AgentView, kind: 'harness' | 'rag', input: HarnessRequest | RagQueryRequest, research: boolean) {
  const turn = view.session.turns[view.session.turns.length - 1];
  if (!turn) throw new Error('Send a task in the native FRAG conversation first.');
  return agentViewSchema.parse(await request(`${path(view.session.sessionId)}/prepare`, {
    version: view.session.version, turnId: turn.id, kind, sourceRequest: parseReselection(kind, input), research,
  }));
}
export async function recoverAgent(view: AgentView) {
  const turn = view.session.turns[view.session.turns.length - 1];
  if (!turn) throw new Error('No current native task.');
  return agentViewSchema.parse(await request(`${path(view.session.sessionId)}/recover`, {
    version: view.session.version, turnId: turn.id,
  }));
}
export function executionBody(view: AgentView) {
  const turn = view.session.turns[view.session.turns.length - 1], preview = view.preview, report = view.report;
  if (!turn || turn.state !== 'running' || !report || !preview || preview.runId !== turn.runId
      || report.run.id !== turn.runId || report.run.sessionId !== view.session.sessionId) {
    throw new Error('Review the current native task and exact request again.');
  }
  const value = preview.preview;
  const fingerprint = 'fingerprint' in value ? value.fingerprint : 'inferenceFingerprint' in value ? value.inferenceFingerprint : value.contextFingerprint;
  if (!value.approvalToken || ('canApprove' in value && value.canApprove === false) || typeof fingerprint !== 'string') {
    throw new Error('Prepare an approvable request first.');
  }
  return { version: view.session.version, turnId: turn.id, runId: report.run.id, runVersion: report.run.version,
    fingerprint, approvalToken: value.approvalToken, approved: true };
}
export async function executeAgent(view: AgentView) {
  return agentViewSchema.parse(await request(`${path(view.session.sessionId)}/execute`, executionBody(view)));
}
