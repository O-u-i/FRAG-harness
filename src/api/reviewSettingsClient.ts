import { agentViewSchema, agentSessionSchema, type AgentView } from '../../shared/contracts/agents';
import { settingsViewSchema, type SettingsView, type ApplicationSettings, type EvidenceSettings, type ConversationSettings } from '../../shared/contracts/reviewSettings';
import { taskContractSchema, type TaskContract } from '../../shared/contracts/governance';
import type { MemorySelection } from '../../shared/contracts/memory';
import { createApiRequestError } from './apiRequestError';
async function request(path: string, method = 'GET', body?: unknown) {
  const response = await fetch(`/api/agents${path}`, { method, ...(body === undefined ? {} : {
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
  if (!response.ok) throw await createApiRequestError(response, 'Settings changed or are unavailable. Reload before saving.');
  return response.json() as Promise<unknown>;
}
const session = (id: string) => `/sessions/${agentSessionSchema.shape.sessionId.parse(id)}`;
export async function fetchReviewSettings(id?: string) {
  return settingsViewSchema.parse(await request(id ? `${session(id)}/settings` : '/settings'));
}
export async function saveApplicationSettings(revision: number, settings: ApplicationSettings) {
  await request('/settings/application', 'PUT', { revision, settings });
}
export async function saveProjectSettings(revision: number, settings: EvidenceSettings) {
  await request('/settings/project', 'PUT', { revision, settings });
}
export async function saveConversationSettings(view: AgentView, revision: number, settings: ConversationSettings | null) {
  const turn = view.session.turns.at(-1);
  if (!turn) throw new Error('A native task is required.');
  await request(`${session(view.session.sessionId)}/settings`, 'PUT', { version: view.session.version, turnId: turn.id, revision, settings });
}
export async function prepareFromSettings(view: AgentView, settings: SettingsView, override: ConversationSettings | null, task: TaskContract, selectedMemory: MemorySelection[]) {
  const turn = view.session.turns.at(-1);
  if (!turn) throw new Error('A native task is required.');
  return agentViewSchema.parse(await request(`${session(view.session.sessionId)}/prepare-settings`, 'POST', {
    version: view.session.version, turnId: turn.id, applicationRevision: settings.application.revision,
    projectRevision: settings.project.revision, conversationRevision: settings.conversation.revision,
    override, task: taskContractSchema.parse(task), selectedMemory,
  }));
}
