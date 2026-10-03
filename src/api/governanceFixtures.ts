import type { PreparedCall, TaskContract } from '../../shared/contracts/governance';

export const reviewTask: TaskContract = { templateId: 'evidence-review-v1', checklist: [] };

export function preparedFixture(purpose: 'context' | 'inference'): PreparedCall {
  const instructions = purpose === 'context' ? 'Compress evidence.' : 'Answer.';
  const maxOutput = purpose === 'context' ? 1500 : 2000;
  return { schemaVersion: 1, purpose, provider: 'fake', model: `fake-${purpose}-v1`,
    endpoint: 'fake://local/responses', transport: 'fake',
    body: JSON.stringify({model: `fake-${purpose}-v1`, instructions, input: '{}',
      max_output_tokens: maxOutput, store: false, tools: []}), binding: '{}',
    timeoutSeconds: 120, maxRetries: 0, estimatedInputTokens: 80, inputBudget: 6000, reservedPercent: 25,
    runTokenLimit: 30000, fingerprint: (purpose === 'context' ? 'a' : 'c').repeat(64) };
}
