import { describe, expect, it } from 'vitest';
import { preparedCallSchema, sourceBindingSchema, taskContractSchema } from '../../shared/contracts/governance';
import { preparedFixture, reviewTask } from './governanceFixtures';
import { harnessRunRequestSchema } from '../../shared/contracts/harness';

describe('governed request contracts', () => {
  it('rejects server prepared specs in caller execution requests', () => {
    const input = { goal: 'Explain the finding', fileSelections: [{relativePath: 'evidence.md',
      locatorIds: ['section-1'], relevanceReason: 'Selected for review'}], contextFingerprint: 'a'.repeat(64),
      approvalToken: 'b'.repeat(48), approved: true, preparedCall: preparedFixture('context') };
    expect(harnessRunRequestSchema.safeParse(input).success).toBe(false);
  });
  it('rejects malformed, unbound or credential-bearing prepared specs', () => {
    const call = preparedFixture('context');
    expect(preparedCallSchema.safeParse(call).success).toBe(true);
    for (const changed of [ {...call, body: '[]'}, {...call, body: '{}'}, {...call, binding: 'invalid'},
      {...call, body: JSON.stringify({...JSON.parse(call.body), model: 'different-model'})},
      {...call, headers: {Authorization: 'synthetic-only'}} ]) {
      expect(preparedCallSchema.safeParse(changed).success).toBe(false);
    }
  });
  it('rejects duplicate checklist identifiers', () => {
    const item = { id: 'critical', text: 'Check evidence support', blocking: true, status: 'pending', reviewed: false };
    expect(taskContractSchema.safeParse({...reviewTask, checklist: [item, item]}).success).toBe(false);
  });
  it('keeps unknown source quality explicit and rejects cross-scope identity shape', () => {
    const unknown = { status: 'unknown', detail: null };
    const source = { identity: {kind: 'local_file', namespace: 'selected-root', resourceId: 'doc', workspaceId: null},
      revision: 'revision', parserVersion: 'parser-v2', locatorIds: ['section-1'], evidenceIds: ['evidence-1'],
      assessment: { authority: unknown, freshness: unknown, relevance: unknown, provenance: unknown,
        permission: 'selected_read_only' } };
    expect(sourceBindingSchema.safeParse(source).success).toBe(true);
    expect(sourceBindingSchema.safeParse({...source, identity: {...source.identity, workspaceId: 'another'}}).success).toBe(false);
    expect(sourceBindingSchema.safeParse({...source, assessment: {...source.assessment,
      authority: {status: 'known', detail: null}}}).success).toBe(false);
  });
});
