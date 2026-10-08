import type { EvidenceSettings, ApplicationSettings, ConversationSettings } from '../../../shared/contracts/reviewSettings';
import type { TaskContract } from '../../../shared/contracts/governance';
import type { EvidenceSelection } from './EvidencePicker';
export function evidenceSettings(value: EvidenceSelection): EvidenceSettings {
  return { mode: value.mode, synthetic: value.mode === 'retrieval' && value.dataset?.datasetId === 'synthetic-risk-review-v1',
    file: value.mode === 'plugin' || value.dataset?.datasetId === 'synthetic-risk-review-v1' ? null : value.file ?? null,
    plugin: value.mode === 'plugin' ? value.plugin ?? null : null };
}
export function checklistTask(template: ApplicationSettings['checklist']): TaskContract {
  return { templateId: 'evidence-review-v1', checklist: template.map((item) => ({ ...item, status: 'pending', reviewed: false })) };
}
export function conversationSettings(selection: EvidenceSelection, research: boolean, task: TaskContract): ConversationSettings {
  return { evidence: evidenceSettings(selection), topK: selection.topK as ConversationSettings['topK'],
    research: selection.mode !== 'plugin' && research, checklist: task.checklist.map(({ id, text, blocking }) => ({ id, text, blocking })) };
}
