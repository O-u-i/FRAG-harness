'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, writeFileSync } = require('node:fs');
const { resolve, join } = require('node:path');
const { startBridge } = require('../model-bridge.cjs');
const { hostEnvironment } = require('../host-launcher.cjs');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');

function fakeVSCode(calls, generate = async function* () { yield '{"synthetic":true}'; }) {
  return { lm: { selectChatModels: async () => [{ id: 'synthetic-model', name: 'Synthetic', vendor: 'customendpoint',
    version: '1', maxInputTokens: 8192, async sendRequest(messages, options, token) {
      calls.push({ messages, options, token }); return { text: generate(token) };
    } }] }, LanguageModelChatMessage: { User: content => ({ role: 'user', content }) },
  CancellationTokenSource: class {
    constructor() { this.token = { isCancellationRequested: false }; }
    cancel() { this.token.isCancellationRequested = true; }
    dispose() {}
  } };
}
function configuration(file, effort = 'high') {
  writeFileSync(file, JSON.stringify([{ vendor: 'customendpoint', models: [{ id: 'synthetic-model' }],
    apiKey: '${input:synthetic-secret}', settings: { 'synthetic-model': { reasoningEffort: effort } } }]));
}
async function fixture(t, generate) {
  const root = mkdtempSync(resolve('.tmp', 'bridge-test-'));
  const file = join(root, 'models.json'); configuration(file);
  const calls = [], bridge = await startBridge(fakeVSCode(calls, generate), file);
  t.after(() => bridge.close());
  const headers = { Authorization: 'Bearer ' + bridge.key, 'Content-Type': 'application/json' };
  const catalog = await (await fetch(bridge.address + '/models', { headers })).json();
  const value = { modelId: catalog[0].id, revision: catalog[0].revision, requestId: 'a'.repeat(64),
    body: { messages: [{ role: 'user', content: 'Instructions' }, { role: 'user', content: '{"outputSchema":{}}' }],
      options: { modelOptions: { max_tokens: 1500 } } } };
  const execute = value => fetch(bridge.address + '/execute', { method: 'POST', headers, body: JSON.stringify(value) });
  return { file, calls, bridge, headers, catalog, value, execute };
}
test('exact API inputs, saved effort provenance, and one-use dispatch', async t => {
  const f = await fixture(t);
  assert.equal(f.catalog[0].effort, 'high');
  assert.ok(!JSON.stringify(f.catalog).includes('synthetic-secret'));
  assert.equal((await f.execute(f.value)).status, 200);
  assert.deepEqual(f.calls[0].messages, f.value.body.messages);
  assert.deepEqual(f.calls[0].options, { modelOptions: { max_tokens: 1500 } });
  assert.equal((await f.execute(f.value)).status, 409);
  assert.equal(f.calls.length, 1);
});
test('configuration changes reject before model access', async t => {
  const f = await fixture(t); configuration(f.file, 'low');
  assert.equal((await f.execute(f.value)).status, 409);
  assert.equal(f.calls.length, 0);
});
test('wrong authorization and web origins cannot access catalog or execution', async t => {
  const f = await fixture(t);
  assert.equal((await fetch(f.bridge.address + '/models')).status, 403);
  assert.equal((await fetch(f.bridge.address + '/models', { headers: { ...f.headers, Origin: 'https://example.invalid' } })).status, 403);
  assert.equal(f.calls.length, 0);
});
test('tool, effort, and request-shape injection fail closed', async t => {
  const f = await fixture(t);
  for (const extra of [{ reasoningEffort: 'max' }, { tools: [] }, { max_tokens: 5000 }]) {
    const value = structuredClone(f.value); Object.assign(value.body.options.modelOptions, extra);
    assert.equal((await f.execute(value)).status, 422);
  }
  assert.equal(f.calls.length, 0);
});
test('provider failure is unknown and cannot be retried', async t => {
  const f = await fixture(t, async function* () { throw new Error('Private provider detail'); });
  const result = await f.execute(f.value);
  assert.equal(result.status, 502); assert.ok(!(await result.text()).includes('Private'));
  assert.equal((await f.execute(f.value)).status, 409); assert.equal(f.calls.length, 1);
});
test('installed environment does not inherit development provider or finance secrets', () => {
  const env = hostEnvironment('C:\\installed', 'synthetic-session-key', {
    PATH: 'C:\\python', OPENAI_API_KEY: 'private', FRAG_RUNTIME_PATH: 'source-state', FINANCE_CORE_TOKEN: 'private' });
  assert.equal(env.OPENAI_API_KEY, undefined); assert.equal(env.FRAG_RUNTIME_PATH, undefined);
  assert.equal(env.FINANCE_CORE_TOKEN, undefined); assert.equal(env.FRAG_BRIDGE_KEY, 'synthetic-session-key');
  assert.equal(env.FRAG_HOST_INSTALLED, '1');
});
test('empty dedicated configuration exposes no models and bridge close is idempotent', async t => {
  const root = mkdtempSync(resolve('.tmp', 'bridge-test-')); const file = join(root, 'models.json');
  writeFileSync(file, '[]'); const calls = [], vscode = fakeVSCode(calls);
  vscode.lm.selectChatModels = async () => { throw Error('Empty configuration must not activate providers'); };
  const bridge = await startBridge(vscode, file);
  t.after(() => bridge.close());
  const response = await fetch(bridge.address + '/models', { headers: { Authorization: 'Bearer ' + bridge.key } });
  assert.deepEqual(await response.json(), []); assert.equal(calls.length, 0);
  await bridge.close(); await bridge.close();
  await assert.rejects(fetch(bridge.address + '/models'));
});
test('nonempty model discovery is bounded before any bridge is exposed', async () => {
  const root = mkdtempSync(resolve('.tmp', 'bridge-test-')); const file = join(root, 'models.json'); configuration(file);
  const sandbox = { module: { exports: {} }, require, Buffer, clearTimeout,
    setTimeout: action => setTimeout(action, 20) };
  vm.runInNewContext(readFileSync(join(__dirname, '../model-bridge.cjs'), 'utf8'), sandbox);
  await assert.rejects(sandbox.module.exports.startBridge({ lm: { selectChatModels: () => new Promise(() => {}) } }, file), /discovery timed out/);
});
