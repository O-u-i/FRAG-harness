import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { adapterIntegrity, execute } from '../worker.mjs';
import { verifyPackage } from '../verify-package.mjs';
import { createGuardedFetch } from '../wire.mjs';

const KEY = 'sk-synthetic-worker-key';
const FP = 'a'.repeat(64);
const ADAPTER = { ...await adapterIntegrity(), hostAdapterHash: 'b'.repeat(64) };
test('reviewed manifest uses LF checkout bytes and passes package verification', async () => {
  const manifest = await readFile(new URL('../vendor/pi-ai/selection-manifest.json', import.meta.url));
  assert.equal(manifest.includes(Buffer.from('\r\n')), false);
  assert.equal((await verifyPackage({ installed: false })).status, 'PASS');
});

function prepared({ purpose = 'context', endpoint = 'https://api.openai.com/v1/responses', model = 'gpt-4.1-mini', ...changes } = {}) {
  const body = { model, instructions: 'Synthetic evidence only.', input: '{}',
    stream: true, store: false, max_output_tokens: purpose === 'research' ? 800 : 1500,
    tools: purpose === 'research' ? [{ type: 'function', name: 'kb_read', description: 'Selected read.',
      strict: true, parameters: { type: 'object', properties: {}, required: [], additionalProperties: false } }] : [],
    text: { format: { type: 'json_schema', name: 'SyntheticOutput', strict: true,
      schema: { type: 'object', properties: {}, required: [], additionalProperties: false } } } };
  return { protocolVersion: 1, apiKey: KEY, preparedCall: { schemaVersion: 1, purpose, provider: 'openai',
    transport: 'pi-responses-v1', model: body.model, endpoint, body: JSON.stringify(body),
    binding: JSON.stringify({ adapter: ADAPTER }), timeoutSeconds: 5, maxRetries: 0, fingerprint: FP, ...changes } };
}
function sol(changes = {}) {
  const input = prepared({ model: 'gpt-6.1-sol', ...changes });
  input.preparedCall.binding = JSON.stringify({ adapter: ADAPTER, nativeReplayVersion: 2 });
  input.preparedCall.body = JSON.stringify({ ...JSON.parse(input.preparedCall.body),
    reasoning: { effort: 'low' }, include: ['reasoning.encrypted_content'] });
  return input;
}
const reasoning = (changes = {}) => ({ type: 'reasoning', id: 'rs_synthetic', summary: [],
  encrypted_content: 'synthetic-opaque-complete-ciphertext', ...changes });
const message = (text = '{"synthetic":true}') => ({ type: 'message', id: 'msg_synthetic', role: 'assistant',
  status: 'completed', content: [{ type: 'output_text', text, annotations: [] }] });
const tool = (argumentsText = '{"selected":true}', changes = {}) => ({ type: 'function_call', id: 'fc_synthetic',
  call_id: 'call_synthetic', name: 'kb_read', arguments: argumentsText, status: 'completed', ...changes });
function response(items, { status = 'completed', usage = { input_tokens: 51, output_tokens: 12 }, omitDone = false,
  omitTerminal = false, extra = [], incompleteReason = 'max_output_tokens', doneItems = items, doneIndices = [], addedItems = [] } = {}) {
  const events = [{ type: 'response.created', response: { id: 'resp_synthetic' } }];
  for (const [output_index, item] of items.entries()) {
    events.push({ type: 'response.output_item.added', output_index,
      item: addedItems[output_index] ?? (item.type === 'function_call' ? { ...item, arguments: '' } : { ...item, content: [] }) });
    if (item.type === 'function_call') events.push({ type: 'response.function_call_arguments.delta',
      output_index, delta: item.arguments.slice(0, 3) });
    if (!omitDone) events.push({ type: 'response.output_item.done', output_index: doneIndices[output_index] ?? output_index,
      item: doneItems[output_index] });
  }
  events.push(...extra);
  if (!omitTerminal) events.push({ type: `response.${status === 'completed' ? 'completed' : 'incomplete'}`,
    response: { id: 'resp_synthetic', status, output: items, usage,
      incomplete_details: status === 'completed' ? null : { reason: incompleteReason } } });
  return new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('') + 'data: [DONE]\n\n',
    { headers: { 'content-type': 'text/event-stream' } });
}
async function run(input = prepared(), responseFactory = () => response([message()])) {
  const wire = [], events = [];
  const result = await execute(input, { emit: value => events.push(value), fetch: async (url, options) => {
    wire.push({ url, ...options }); return responseFactory();
  } });
  return { result, wire, events };
}

test('ordinary structured request uses exact frozen bytes and backend-only explicit key', async () => {
  const input = prepared();
  const { result, wire, events } = await run(input);
  assert.equal(result.ok, true);
  assert.deepEqual(result.response, { status: 'completed', outputText: '{"synthetic":true}', calls: [],
    usage: { inputTokens: 51, outputTokens: 12 } });
  assert.equal(wire.length, 1);
  assert.equal(wire[0].url, input.preparedCall.endpoint);
  assert.equal(wire[0].body, input.preparedCall.body);
  assert.equal(wire[0].redirect, 'error');
  assert.equal(wire[0].headers.get('authorization'), `Bearer ${KEY}`);
  assert.deepEqual(events, [{ protocolVersion: 1, event: 'dispatch', fingerprint: FP }]);
  assert.equal(JSON.stringify([result, events]).includes(KEY), false);
});

test('native complete tool calls preserve raw IDs and raw argument strings', async () => {
  const { result } = await run(prepared({ purpose: 'research' }), () => response([tool('{"identity":{"kind":"synthetic"}}')]));
  assert.equal(result.ok, true);
  assert.deepEqual(result.response.calls, [{ callId: 'call_synthetic', itemId: 'fc_synthetic', name: 'kb_read',
    argumentsText: '{"identity":{"kind":"synthetic"}}' }]);
});

for (const text of ['{"selected":', '{"selected":true,"selected":false}', '{"path":"bad\\escape"}']) {
  test(`raw invalid arguments remain untouched for Python strict validation: ${text}`, async () => {
    const { result } = await run(prepared({ purpose: 'research' }), () => response([tool(text)]));
    assert.equal(result.ok, true);
    assert.equal(result.response.calls[0].argumentsText, text);
  });
}

for (const [name, changes] of [
  ['reasoning model', { model: 'gpt-5' }], ['noncanonical endpoint', { endpoint: 'https://unapproved.example:443/v1/responses' }],
  ['retry budget', { maxRetries: 1 }], ['transport', { transport: 'responses-v1' }],
  ['timeout', { timeoutSeconds: 121 }], ['fingerprint', { fingerprint: 'invalid' }],
  ['adapter version', { binding: JSON.stringify({ adapter: { ...ADAPTER, version: '2.0.0' } }) }],
  ['manifest hash', { binding: JSON.stringify({ adapter: { ...ADAPTER, selectionManifestHash: 'c'.repeat(64) } }) }],
  ['worker hash', { binding: JSON.stringify({ adapter: { ...ADAPTER, workerFiles: { ...ADAPTER.workerFiles, 'worker.mjs': 'c'.repeat(64) } } }) }],
  ['invalid host hash', { binding: JSON.stringify({ adapter: { ...ADAPTER, hostAdapterHash: 'invalid' } }) }],
  ['additional adapter field', { binding: JSON.stringify({ adapter: { ...ADAPTER, extra: true } }) }],
]) {
  test(`pre-dispatch rejection: ${name}`, async () => {
    const { result, wire, events } = await run(prepared(changes));
    assert.equal(result.ok, false); assert.equal(result.dispatched, false);
    assert.equal(wire.length, 0); assert.equal(events.length, 0);
  });
}

for (const [name, patch] of [
  ['body model', { model: 'gpt-4.1' }], ['storage', { store: true }], ['stream', { stream: false }],
  ['cap', { max_output_tokens: 2001 }], ['background', { background: true }], ['server conversation', { previous_response_id: 'resp_old' }],
  ['reasoning', { reasoning: { effort: 'low' } }], ['key in payload', { input: KEY }],
  ['unknown tool', { tools: [{ type: 'web_search' }] }],
]) {
  test(`frozen body policy rejects ${name} before SDK dispatch`, async () => {
    const input = prepared(); input.preparedCall.body = JSON.stringify({ ...JSON.parse(input.preparedCall.body), ...patch });
    const { result, wire } = await run(input);
    assert.equal(result.ok, false); assert.equal(result.dispatched, false); assert.equal(wire.length, 0);
  });
}

for (const status of [302, 429, 500]) {
  test(`HTTP ${status} fails once without retry`, async () => {
    const { result, wire, events } = await run(prepared(), () => new Response('{}', { status, headers: { location: 'https://unapproved.example/' } }));
    assert.equal(result.ok, false); assert.equal(result.errorCode, 'RAG_PROVIDER_ERROR');
    assert.equal(wire.length, 1); assert.equal(events.length, 1);
  });
}

test('unknown network outcome remains explicit without retry or raw diagnostics', async () => {
  const { result, wire } = await run(prepared(), () => { throw new Error(`Sensitive failure ${KEY}`); });
  assert.equal(result.errorCode, 'RAG_OUTCOME_UNKNOWN'); assert.equal(result.dispatched, true);
  assert.equal(wire.length, 1); assert.equal(JSON.stringify(result).includes(KEY), false);
});

test('refusal and incomplete output are distinct', async () => {
  const refused = message(); refused.content = [{ type: 'refusal', refusal: 'Synthetic refusal' }];
  assert.equal((await run(prepared(), () => response([refused]))).result.errorCode, 'RAG_REFUSAL');
  assert.equal((await run(prepared(), () => response([message()], { status: 'incomplete' }))).result.errorCode, 'RAG_INCOMPLETE');
});

test('missing terminal response cannot become a completed request', async () => {
  const { result } = await run(prepared(), () => response([message()], { omitTerminal: true }));
  assert.equal(result.ok, false); assert.equal(result.errorCode, 'RAG_OUTCOME_UNKNOWN');
});

test('unfinished streamed call cannot become an executable proposal', async () => {
  const { result } = await run(prepared({ purpose: 'research' }), () => response([tool()], { omitDone: true }));
  assert.equal(result.ok, false); assert.equal(result.errorCode, 'RAG_OUTPUT_INVALID');
});

test('mixed finish text and native calls fail closed', async () => {
  const { result } = await run(prepared({ purpose: 'research' }), () => response([message(), tool()]));
  assert.equal(result.ok, false); assert.equal(result.errorCode, 'RAG_OUTPUT_INVALID');
});

test('unknown tools, duplicate calls, reasoning items and invalid usage fail closed', async () => {
  for (const items of [[tool('{}', { name: 'finance_write' })],
    [tool(), tool('{}', { id: 'fc_second' })],
    [{ type: 'reasoning', id: 'rs_synthetic', status: 'completed', summary: [] }]]) {
    assert.equal((await run(prepared({ purpose: 'research' }), () => response(items))).result.ok, false);
  }
  assert.equal((await run(prepared(), () => response([message()], { usage: {} }))).result.errorCode, 'RAG_OUTPUT_INVALID');
});

test('usage includes cached input exactly once from the raw provider total', async () => {
  const { result } = await run(prepared(), () => response([message()], {
    usage: { input_tokens: 51, output_tokens: 12, total_tokens: 63,
      input_tokens_details: { cached_tokens: 40 }, output_tokens_details: { reasoning_tokens: 4 } },
  }));
  assert.deepEqual(result.response.usage, { inputTokens: 51, outputTokens: 12 });
});

test('model text cannot echo the API key through stdout protocol', async () => {
  const { result } = await run(prepared(), () => response([message(KEY)]));
  assert.equal(result.errorCode, 'RAG_OUTPUT_INVALID'); assert.equal(JSON.stringify(result).includes(KEY), false);
});

test('malformed input cannot copy the key into an error fingerprint', async () => {
  const { result, wire } = await run(prepared({ fingerprint: KEY }));
  assert.equal(result.ok, false); assert.equal(result.fingerprint, '');
  assert.equal(JSON.stringify(result).includes(KEY), false); assert.equal(wire.length, 0);
});

test('oversize stream and final protocol message are bounded', async () => {
  const huge = new Response('x'.repeat(1024 * 1024 + 1), { headers: { 'content-type': 'text/event-stream' } });
  assert.equal((await run(prepared(), () => huge)).result.errorCode, 'RAG_OUTCOME_UNKNOWN');
  assert.equal((await run(prepared(), () => response([message('x'.repeat(256 * 1024))]))).result.errorCode, 'RAG_OUTPUT_INVALID');
});

test('ambient auth and endpoint variables do not replace explicit configuration', async () => {
  const previous = { key: process.env.OPENAI_API_KEY, base: process.env.OPENAI_BASE_URL };
  try {
    process.env.OPENAI_API_KEY = 'sk-unapproved-ambient-key'; process.env.OPENAI_BASE_URL = 'https://unapproved.example/';
    const { result, wire } = await run();
    assert.equal(result.ok, true); assert.equal(wire[0].url, 'https://api.openai.com/v1/responses');
    assert.equal(wire[0].headers.get('authorization'), `Bearer ${KEY}`);
  } finally {
    if (previous.key === undefined) delete process.env.OPENAI_API_KEY; else process.env.OPENAI_API_KEY = previous.key;
    if (previous.base === undefined) delete process.env.OPENAI_BASE_URL; else process.env.OPENAI_BASE_URL = previous.base;
  }
});

test('production entry rejects a loopback endpoint and emits no secret or stderr', async () => {
  const env = { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, TEMP: process.env.TEMP };
  const child = spawn(process.execPath, [new URL('../worker.mjs', import.meta.url).pathname.replace(/^\/(\w:)/, '$1')],
    { env, stdio: ['pipe', 'pipe', 'pipe'] });
  let out = '', err = '';
  child.stdout.on('data', chunk => { out += chunk; }); child.stderr.on('data', chunk => { err += chunk; });
  child.stdin.end(JSON.stringify(prepared({ endpoint: 'http://127.0.0.1:1/v1/responses' })));
  const [code] = await once(child, 'close');
  assert.equal(code, 0); assert.equal(err, ''); assert.equal(out.includes(KEY), false);
  const values = out.trim().split('\n').map(value => JSON.parse(value));
  assert.equal(values.length, 1); assert.equal(values[0].dispatched, false);
});

test('Sol uses exact frozen low/include profile and returns complete ordered raw output', async () => {
  for (const purpose of ['research', 'context', 'inference']) {
    const items = [reasoning(), { ...message(), phase: 'final_answer' }];
    const input = sol({ purpose });
    const { result, wire } = await run(input, () => response(items, { usage: {
      input_tokens: 51, output_tokens: 12, input_tokens_details: { cached_tokens: 40 },
      output_tokens_details: { reasoning_tokens: 7 } } }));
    assert.equal(result.ok, true, JSON.stringify(result));
    assert.deepEqual(result.response.outputItems, items);
    assert.equal(result.response.outputText, '{"synthetic":true}');
    assert.deepEqual(result.response.usage, { inputTokens: 51, outputTokens: 12 });
    assert.equal(wire.length, 1); assert.equal(wire[0].body, input.preparedCall.body);
    assert.equal(JSON.parse(wire[0].body).model, 'gpt-6.1-sol');
    assert.deepEqual(JSON.parse(wire[0].body).reasoning, { effort: 'low' });
    assert.deepEqual(JSON.parse(wire[0].body).include, ['reasoning.encrypted_content']);
  }
});

test('Sol native continuation replays encrypted items and commentary in original wire order', async () => {
  const items = [reasoning({ status: 'completed', summary: [{ type: 'summary_text', text: 'Synthetic summary.' }] }),
    { ...message('Reading selected synthetic evidence.'), phase: 'commentary' }, tool(),
    reasoning({ id: 'rs_second' }), tool('{"selected":false}', { id: 'fc_second', call_id: 'call_second' })];
  const first = await run(sol({ purpose: 'research' }), () => response(items));
  assert.equal(first.result.ok, true, JSON.stringify(first.result));
  assert.equal(first.result.response.outputText, '');
  assert.deepEqual(first.result.response.outputItems, items);
  assert.deepEqual(first.result.response.calls.map(call => call.callId), ['call_synthetic', 'call_second']);
  const next = sol({ purpose: 'research' });
  const outputs = first.result.response.calls.map(call => ({ type: 'function_call_output', call_id: call.callId,
    output: JSON.stringify({ status: 'completed', selected: true }) }));
  next.preparedCall.body = JSON.stringify({ ...JSON.parse(next.preparedCall.body),
    input: [{ role: 'user', content: [{ type: 'input_text', text: '{}' }] }, ...items, ...outputs] });
  const final = await run(next, () => response([reasoning({ id: 'rs_finish' }), { ...message(), phase: 'final_answer' }]));
  assert.equal(final.result.ok, true);
  assert.deepEqual(JSON.parse(final.wire[0].body).input.slice(1), [...items, ...outputs]);
  assert.equal(final.wire[0].body, next.preparedCall.body);
});

test('Sol completed output preserves indexed order despite reversed done-event arrival', async () => {
  const items = [reasoning(), tool(), reasoning({ id: 'rs_second' }), tool('{}', { id: 'fc_second', call_id: 'call_second' })];
  const extra = [...items.entries()].reverse().map(([output_index, item]) => ({ type: 'response.output_item.done', output_index, item }));
  const { result } = await run(sol({ purpose: 'research' }), () => response(items, { omitDone: true, extra }));
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.deepEqual(result.response.outputItems, items);
  assert.deepEqual(result.response.calls.map(call => call.callId), ['call_synthetic', 'call_second']);
});

test('Sol added reasoning ciphertext and argument fragments cannot replace completed values', async () => {
  const items = [reasoning(), tool('{"selected":true}')];
  const { result } = await run(sol({ purpose: 'research' }), () => response(items, { addedItems: [
    reasoning({ status: 'in_progress', encrypted_content: 'synthetic-partial-ciphertext' }),
    tool('{"selected":', { status: 'in_progress' })] }));
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.deepEqual(result.response.outputItems, items);
  assert.equal(result.response.calls[0].argumentsText, '{"selected":true}');
});

test('Sol complete function call preserves absent status but rejects explicit partial status', async () => {
  const item = tool(); delete item.status;
  const { result } = await run(sol({ purpose: 'research' }), () => response([reasoning(), item]));
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.deepEqual(result.response.outputItems[1], item);
  assert.equal(Object.hasOwn(result.response.outputItems[1], 'status'), false);
  for (const status of ['in_progress', 'incomplete', null]) {
    assert.equal((await run(sol({ purpose: 'research' }), () => response([reasoning(), tool('{}', { status })]))).result.ok, false);
  }
  assert.equal((await run(prepared({ purpose: 'research' }), () => response([item]))).result.ok, false);
});

for (const missing of [undefined, null]) {
  test(`Sol accepts only terminal ciphertext enrichment from ${String(missing)}`, async () => {
    const completed = reasoning();
    const before = { ...completed };
    if (missing === undefined) delete before.encrypted_content; else before.encrypted_content = null;
    const { result } = await run(sol({ purpose: 'research' }), () => response([completed, tool()], { doneItems: [before, tool()] }));
    assert.equal(result.ok, true, JSON.stringify(result));
    assert.deepEqual(result.response.outputItems[0], completed);
    assert.equal(Object.hasOwn(result.response.outputItems[0], 'status'), false);
  });
}

for (const [name, patch] of [
  ['different effort', { reasoning: { effort: 'medium' } }],
  ['extra reasoning option', { reasoning: { effort: 'low', summary: 'auto' } }],
  ['missing reasoning', { reasoning: undefined }], ['extra include', { include: ['reasoning.encrypted_content', 'web_search_call.action.sources'] }],
  ['missing include', { include: undefined }], ['output cap', { max_output_tokens: 801 }],
]) {
  test(`Sol rejects unapproved frozen ${name} before dispatch`, async () => {
    const input = sol({ purpose: 'research' });
    input.preparedCall.body = JSON.stringify({ ...JSON.parse(input.preparedCall.body), ...patch });
    const { result, wire, events } = await run(input);
    assert.equal(result.ok, false); assert.equal(result.dispatched, false);
    assert.equal(wire.length, 0); assert.equal(events.length, 0);
  });
}

test('Sol rejects missing replay version and model substitution before dispatch', async () => {
  for (const change of ['binding', 'model']) {
    const input = sol();
    if (change === 'binding') input.preparedCall.binding = JSON.stringify({ adapter: ADAPTER });
    else input.preparedCall.model = 'gpt-6.1-sol-substitute';
    const { result, wire } = await run(input);
    assert.equal(result.ok, false); assert.equal(result.dispatched, false); assert.equal(wire.length, 0);
  }
});

test('Sol rejects incomplete reasoning, ciphertext conflicts and other done-terminal changes', async () => {
  for (const items of [[reasoning({ status: 'in_progress' }), tool()], [reasoning({ status: 'incomplete' }), tool()],
    [reasoning({ status: null }), tool()], [reasoning({ encrypted_content: null }), tool()],
    [reasoning({ encrypted_content: '' }), tool()], [{ type: 'web_search_call', id: 'ws_unknown', status: 'completed' }]]) {
    assert.equal((await run(sol({ purpose: 'research' }), () => response(items))).result.ok, false);
  }
  for (const before of [reasoning({ encrypted_content: 'synthetic-conflicting-ciphertext' }), reasoning({ encrypted_content: '' }),
    { ...reasoning(), encrypted_content: null, summary: [{ type: 'summary_text', text: 'Changed summary' }] }]) {
    assert.equal((await run(sol({ purpose: 'research' }), () => response([reasoning(), tool()], { doneItems: [before, tool()] }))).result.ok, false);
  }
  const missing = reasoning(); delete missing.encrypted_content;
  assert.equal((await run(sol({ purpose: 'research' }), () => response([missing, tool()]))).result.ok, false);
});

test('Sol final reasoning preserves optional absent or null ciphertext fields', async () => {
  for (const missing of [undefined, null]) {
    const item = reasoning();
    if (missing === undefined) delete item.encrypted_content; else item.encrypted_content = null;
    const { result } = await run(sol(), () => response([item, { ...message(), phase: null }]));
    assert.equal(result.ok, true); assert.deepEqual(result.response.outputItems[0], item);
    assert.equal(result.response.outputItems[1].phase, null);
  }
});

test('Sol commentary is replayable but cannot replace final JSON or mix a final answer with tools', async () => {
  const commentary = { ...message('Synthetic commentary.'), phase: 'commentary' };
  const { result } = await run(sol(), () => response([reasoning(), commentary, { ...message(), id: 'msg_final', phase: 'final_answer' }]));
  assert.equal(result.ok, true); assert.equal(result.response.outputText, '{"synthetic":true}');
  assert.equal((await run(sol(), () => response([reasoning(), commentary]))).result.ok, false);
  assert.equal((await run(sol({ purpose: 'research' }), () => response([reasoning(), { ...message(), phase: 'final_answer' }, tool()]))).result.ok, false);
  assert.equal((await run(sol(), () => response([{ ...message(), phase: 'unknown' }]))).result.ok, false);
});

test('Sol rejects duplicate IDs, wrong output indices, extra raw fields and unfinished reasoning', async () => {
  for (const options of [{ doneIndices: [1, 0] }, { doneIndices: [0, 0] }, { doneIndices: [-1, 1] }, { omitDone: true }]) {
    assert.equal((await run(sol(), () => response([reasoning(), message()], options))).result.ok, false);
  }
  for (const items of [[reasoning(), reasoning()], [reasoning({ unexpected: true }), message()],
    [{ ...message(), content: [{ type: 'output_text', text: '{}', annotations: [{ type: 'url_citation' }] }] }]]) {
    assert.equal((await run(sol(), () => response(items))).result.ok, false);
  }
});

test('Sol refuses, reports incomplete and unknown outcomes without retry or encrypted fragment replay', async () => {
  const refused = { ...message(), content: [{ type: 'refusal', refusal: 'Synthetic refusal.' }] };
  assert.equal((await run(sol(), () => response([reasoning(), refused]))).result.errorCode, 'RAG_REFUSAL');
  assert.equal((await run(sol(), () => response([reasoning()], { status: 'incomplete' }))).result.errorCode, 'RAG_INCOMPLETE');
  const missing = await run(sol(), () => response([reasoning()], { omitTerminal: true }));
  assert.equal(missing.result.errorCode, 'RAG_OUTCOME_UNKNOWN'); assert.equal(missing.wire.length, 1);
  const failed = await run(sol(), () => { throw new Error('Synthetic transport failure.'); });
  assert.equal(failed.result.errorCode, 'RAG_OUTCOME_UNKNOWN'); assert.equal(failed.wire.length, 1);
  const redirect = await run(sol(), () => new Response('{}', { status: 302, headers: { location: 'https://other.example/v1/responses' } }));
  assert.equal(redirect.result.errorCode, 'RAG_PROVIDER_ERROR'); assert.equal(redirect.wire.length, 1);
});

test('Sol ciphertext and raw item counts remain within protocol limits', async () => {
  assert.equal((await run(sol(), () => response([reasoning({ encrypted_content: 'x'.repeat(256 * 1024) }), message()]))).result.errorCode, 'RAG_OUTPUT_INVALID');
  const items = Array.from({ length: 65 }, (_, index) => reasoning({ id: `rs_${index}` }));
  assert.equal((await run(sol(), () => response(items))).result.errorCode, 'RAG_OUTPUT_INVALID');
});

test('canonical HTTPS prepared destination is forwarded exactly with no ambient routing', async () => {
  for (const endpoint of ['https://relay.synthetic.example/v1/responses', 'https://localhost/v1/responses', 'https://127.0.0.1/v1/responses']) {
    const input = sol({ endpoint });
    const { result, wire } = await run(input, () => response([reasoning(), message()]));
    assert.equal(result.ok, true); assert.equal(wire.length, 1);
    assert.equal(wire[0].url, input.preparedCall.endpoint); assert.equal(wire[0].redirect, 'error');
  }
});

for (const endpoint of ['https://relay.synthetic.example:443/v1/responses', 'https://Relay.synthetic.example/v1/responses',
  'https://relay.synthetic.example/v1/../v1/responses', 'https://relay.synthetic.example/v1/%72esponses',
  'https://user@relay.synthetic.example/v1/responses', 'https://relay.synthetic.example/v1/responses?x=1',
  'https://relay.synthetic.example/v1/responses#part', 'https://relay.synthetic.example./v1/responses']) {
  test(`canonical HTTPS rejects ambiguous prepared destination ${endpoint}`, async () => {
    const { result, wire } = await run(sol({ endpoint }));
    assert.equal(result.ok, false); assert.equal(result.dispatched, false); assert.equal(wire.length, 0);
  });
}

function guardFixture() {
  const input = prepared(), call = input.preparedCall, body = JSON.parse(call.body);
  const wire = [], events = [], state = { dispatched: false, attempts: 0, failure: null };
  const guard = createGuardedFetch({ call, body, apiKey: KEY, state, signal: new AbortController().signal,
    emit: async value => events.push(value), fetch: async (url, options) => {
      wire.push({ url, ...options }); return new Response('{}');
    } });
  const init = { method: 'POST', headers: { authorization: `Bearer ${KEY}`, 'content-type': 'application/json' }, body: call.body };
  return { input, call, body, wire, events, state, guard, init };
}

for (const change of ['destination', 'method', 'body', 'auth', 'content-type']) {
  test(`actual final SDK wire tamper rejected before forwarding: ${change}`, async () => {
    const value = guardFixture();
    const url = change === 'destination' ? 'https://unapproved.example/v1/responses' : value.call.endpoint;
    if (change === 'method') value.init.method = 'PUT';
    if (change === 'body') value.init.body = JSON.stringify({ ...value.body, max_output_tokens: 1999 });
    if (change === 'auth') value.init.headers.authorization = 'Bearer synthetic-unapproved';
    if (change === 'content-type') value.init.headers['content-type'] = 'text/plain';
    await assert.rejects(value.guard(url, value.init));
    assert.equal(value.wire.length, 0); assert.equal(value.events.length, 0); assert.equal(value.state.dispatched, false);
  });
}

test('second SDK fetch is blocked, including a hypothetical automatic retry', async () => {
  const value = guardFixture();
  await value.guard(value.call.endpoint, value.init);
  await assert.rejects(value.guard(value.call.endpoint, value.init));
  assert.equal(value.wire.length, 1); assert.equal(value.events.length, 1); assert.equal(value.state.failure, 'RAG_PROVIDER_ERROR');
});

test('dispatch receipt awaits completion before network forwarding', async () => {
  const value = guardFixture();
  let finishReceipt;
  const gate = new Promise(resolve => { finishReceipt = resolve; });
  const guard = createGuardedFetch({ call: value.call, body: value.body, apiKey: KEY, state: value.state,
    signal: new AbortController().signal, emit: () => gate,
    fetch: async () => { value.wire.push('sent'); return new Response('{}'); } });
  const pending = guard(value.call.endpoint, value.init);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(value.wire.length, 0);
  finishReceipt(); await pending; assert.equal(value.wire.length, 1);
});

test('real loopback HTTP server receives exact SDK-approved frozen bytes and supplies SSE', async () => {
  const observed = [];
  const server = createServer(async (request, outgoing) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    observed.push({ method: request.method, path: request.url, body, authorization: request.headers.authorization });
    outgoing.writeHead(200, { 'content-type': 'text/event-stream' });
    outgoing.end(await response([message()]).text());
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  try {
    const input = prepared({ endpoint: `http://127.0.0.1:${server.address().port}/v1/responses` });
    const result = await execute(input, { fetch: globalThis.fetch });
    assert.equal(result.ok, true, JSON.stringify({ result, observedCount: observed.length }));
    assert.deepEqual(observed, [{ method: 'POST', path: '/v1/responses', body: input.preparedCall.body, authorization: `Bearer ${KEY}` }]);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
