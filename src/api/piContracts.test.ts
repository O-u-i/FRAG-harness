import { describe, expect, it } from 'vitest';
import { preparedCallSchema } from '../../shared/contracts/governance';
import { nativeResearchReplaySchema } from '../../shared/contracts/research';
import { attemptRecordSchema } from '../../shared/contracts/runtime';
import { preparedFixture } from './governanceFixtures';

const hash = 'a'.repeat(64);
const adapter = {name: 'pi-openai-responses', version: '1.0.0',
  piCommit: 'a13d35a742c6ef8462812a28fbe1d8c8b7431c32', protocolVersion: 1, wireVersion: 1,
  selectionManifestHash: hash, hostAdapterHash: hash,
  workerFiles: {'worker.mjs': hash, 'wire.mjs': hash, 'verify-package.mjs': hash}};
const piCall = {...preparedFixture('research'), provider: 'openai', model: 'gpt-4.1-mini',
  transport: 'pi-responses-v1', endpoint: 'https://api.openai.com/v1/responses',
  body: JSON.stringify({model: 'gpt-4.1-mini', instructions: 'Collect only selected evidence.',
    input: [{role: 'user', content: [{type: 'input_text', text: '{"manifest":[]}'}]}],
    stream: true, store: false, tools: [], max_output_tokens: 800}),
  binding: JSON.stringify({adapter, wireSchemaHash: hash})};
const native = {version: 1, calls: [{callId: 'call_raw|upstream', itemId: 'fc_raw', name: 'kb_read',
  argumentsText: '{"identity":{}}', hostCallId: `pi_${hash}`}]};

describe('Pi approval and durable replay contracts', () => {
  it('accepts the exact streaming preview while preserving legacy fixed requests', () => {
    expect(preparedCallSchema.parse(piCall).transport).toBe('pi-responses-v1');
    expect(preparedCallSchema.parse(preparedFixture('context')).transport).toBe('fake');
    for (const change of [
      {endpoint: 'http://other.example/v1/responses'},
      {body: JSON.stringify({...JSON.parse(piCall.body), stream: false})},
      {body: JSON.stringify({...JSON.parse(piCall.body), input: '{}'})},
      {binding: JSON.stringify({adapter: {...adapter, version: 'unreviewed'}, wireSchemaHash: hash})},
      {binding: JSON.stringify({adapter: {...adapter, hostAdapterHash: 'missing'}, wireSchemaHash: hash})},
    ]) expect(preparedCallSchema.safeParse({...piCall, ...change}).success).toBe(false);
  });

  it('binds a configured HTTPS Sol route and preserves complete raw reasoning history', () => {
    const sol = {...piCall, model: 'gpt-6.1-sol', endpoint: 'https://relay.example/v1/responses',
      body: JSON.stringify({...JSON.parse(piCall.body), model: 'gpt-6.1-sol',
        reasoning: {effort: 'low'}, include: ['reasoning.encrypted_content']}),
      binding: JSON.stringify({...JSON.parse(piCall.binding), nativeReplayVersion: 2})};
    expect(preparedCallSchema.parse(sol).endpoint).toBe(sol.endpoint);
    const outputItems = [
      {type: 'reasoning', id: 'rs_1', summary: [], encrypted_content: 'opaque-synthetic'},
      {type: 'message', id: 'msg_1', role: 'assistant', status: 'completed', phase: 'commentary',
        content: [{type: 'output_text', text: 'I will read selected evidence.', annotations: []}]},
      {type: 'function_call', id: 'fc_raw', call_id: 'call_raw|upstream', name: 'kb_read', arguments: '{"identity":{}}'},
    ];
    const replay = {version: 2, calls: native.calls, outputItems};
    expect(nativeResearchReplaySchema.parse(replay)).toEqual(replay);
    expect(JSON.stringify(nativeResearchReplaySchema.parse(native))).toBe(JSON.stringify(native));
    const attempt = {id: 'sol-attempt', stage: 'research', status: 'completed', preparedCall: sol,
      createdAt: '2026-10-04T00:00:00Z', structuralValidation: 'PASS', nativeReplay: replay, nativeReplayDigest: hash};
    expect(attemptRecordSchema.parse(attempt).nativeReplay).toEqual(replay);
    for (const change of [
      {...replay, version: 3}, {...replay, outputItems: [...outputItems, outputItems[0]]},
      {...replay, outputItems: [{...outputItems[0], encrypted_content: null}, ...outputItems.slice(1)]},
      {...replay, calls: [{...native.calls[0], itemId: 'fc_foreign'}]},
      {...replay, outputItems: [{...outputItems[0], status: 'in_progress'}, ...outputItems.slice(1)]},
      {...replay, outputItems: [{...outputItems[0], apiKey: 'private'}, ...outputItems.slice(1)]},
    ]) expect(nativeResearchReplaySchema.safeParse(change).success).toBe(false);
    const finish = {version: 2, calls: [], outputItems: [{type: 'message', id: 'msg_finish', role: 'assistant',
      status: 'completed', phase: null, content: [{type: 'output_text', text: '{"action":"finish"}', annotations: []}]}]};
    expect(nativeResearchReplaySchema.parse(finish)).toEqual(finish);
  });

  it('keeps original native IDs and requires complete typed replay records', () => {
    expect(nativeResearchReplaySchema.parse(native).calls[0].callId).toBe('call_raw|upstream');
    const attempt = {id: 'attempt', stage: 'research', status: 'completed', preparedCall: piCall,
      createdAt: '2026-10-04T00:00:00Z', structuralValidation: 'PASS', nativeReplay: native, nativeReplayDigest: hash};
    expect(attemptRecordSchema.parse(attempt).nativeReplay?.calls[0].hostCallId).toBe(`pi_${hash}`);
    expect(nativeResearchReplaySchema.safeParse({...native, calls: [...native.calls, ...native.calls]}).success).toBe(false);
    expect(nativeResearchReplaySchema.safeParse({...native, calls: [{...native.calls[0], apiKey: 'private'}]}).success).toBe(false);
    expect(attemptRecordSchema.safeParse({...attempt, nativeReplayDigest: 'bad'}).success).toBe(false);
    expect(attemptRecordSchema.safeParse({...attempt, approvalToken: 'reusable'}).success).toBe(false);
  });
});
