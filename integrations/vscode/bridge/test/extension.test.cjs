'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function fixture(t, options = {}) {
  const root = fs.mkdtempSync(path.resolve('.tmp', 'extension-test-'));
  const storage = path.join(root, 'User', 'globalStorage', 'frag-local.frag-bridge');
  fs.mkdirSync(storage, { recursive: true });
  const file = path.join(root, 'User', 'chatLanguageModels.json'); fs.writeFileSync(file, '[]');
  const defaults = { remoteAgentHosts: [], remoteAgentHostsEnabled: false, remoteAgentHostsAutoConnect: false };
  for (const key of options.missing || []) delete defaults[key];
  const values = { ...options.values }, updates = [], errors = [], info = [], commands = new Map();
  const stats = { launched: 0, bridges: 0, stopped: 0, closed: 0, models: 0, dialogs: 0 };
  const bridge = { async close() { stats.closed++; if (options.closeFailure?.()) throw Error('secret cleanup detail'); } };
  const owned = { name: 'FRAG · 12345678', address: 'ws://127.0.0.1:19999/api/agents/ahp',
    origin: 'http://127.0.0.1:19999', project: root, bridge,
    async stop() { stats.stopped++; if (options.stopFailure?.()) throw Error('secret shutdown detail'); } };
  const chat = { get: key => Object.hasOwn(values, key) ? values[key] : defaults[key],
    // VS Code inspect returns an object even for an unregistered key with no default.
    inspect: key => ({ key: 'chat.' + key, defaultValue: defaults[key], globalValue: values[key] }),
    async update(key, value) {
      updates.push({ key, value });
      if (!Object.hasOwn(defaults, key)) throw Error(`chat.${key} is not a registered configuration`);
      if (options.writeFailure?.(key, value, updates.length)) {
        if (options.writeBeforeReject) values[key] = structuredClone(value);
        throw Error('secret original write detail');
      }
      if (value === undefined) delete values[key]; else values[key] = structuredClone(value);
    } };
  const extensionSettings = { get: key => key === 'supportAgentsWindow' ? { 'other.extension': true } : undefined,
    inspect: () => ({ defaultValue: {} }), update: async (key, value) => { updates.push({ key, value }); } };
  const vscode = { env: { appHost: 'desktop', remoteName: options.remoteName, clipboard: { writeText: async () => {} } },
    workspace: { isTrusted: options.trusted !== false, getConfiguration: section => section === 'chat' ? chat
      : section === 'extensions' ? extensionSettings : { get: key => key === 'modelConfigFile'
        ? (Object.hasOwn(options, 'configFile') ? options.configFile : file) : root } },
    window: { showOpenDialog: async () => { stats.dialogs++; return options.cancel ? undefined : [{ scheme: 'file', fsPath: root }]; },
      showErrorMessage: async text => { errors.push(text); if (options.pendingNotification) await new Promise(() => {}); },
      showInformationMessage: async text => { info.push(text); if (options.pendingNotification) await new Promise(() => {}); return options.choice; } },
    ConfigurationTarget: { Global: 1 }, commands: { registerCommand: (id, action) => { commands.set(id, action); return { dispose() {} }; },
      getCommands: async () => [], executeCommand: async id => { info.push(id); } },
    lm: { selectChatModels: async () => [], sendRequest: async () => { stats.models++; throw Error('No model calls authorized'); } } };
  const sandbox = { module: { exports: {} }, process, require: id => id === 'vscode' ? vscode
    : id === './model-bridge.cjs' ? { startBridge: async () => { stats.bridges++; if (options.bridgeFailure) throw Error('secret config detail'); return bridge; } }
      : id === './host-launcher.cjs' ? { launchHost: async () => { stats.launched++; if (options.waitLaunch) await options.waitLaunch;
        if (options.launchFailure) { const error = Error('secret startup detail'); if (options.failedOwnedHost) error.ownedHost = owned; throw error; } return owned; } } : require(id) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extension.cjs'), 'utf8'), sandbox);
  sandbox.module.exports.activate({ globalStorageUri: { scheme: options.storageScheme || 'vscode-userdata', fsPath: storage }, subscriptions: [] });
  t.after(() => assert.equal(stats.models, 0));
  return { root, file, stats, values, defaults, updates, errors, info, owned,
    start: () => commands.get('frag.start')(), stop: () => commands.get('frag.stop')(),
    configure: () => commands.get('frag.configure')(), deactivate: sandbox.module.exports.deactivate };
}
test('unregistered configuration rejects the real Start command before dialogs or processes', async t => {
  const f = fixture(t, { missing: ['remoteAgentHosts'], values: { remoteAgentHosts: [] } }); await f.start();
  assert.match(f.errors[0], /no registered chat.remoteAgentHosts/);
  assert.equal(f.stats.launched + f.stats.bridges + f.stats.dialogs, 0); assert.equal(f.updates.length, 0);
});
test('all required settings, local trust and explicit profile binding are preflighted', async t => {
  for (const options of [{ missing: ['remoteAgentHostsAutoConnect'] }, { missing: ['remoteAgentHostsEnabled'] },
    { remoteName: 'ssh-remote' }, { trusted: false }, { configFile: '' }, { configFile: 'C:\\other-profile\\chatLanguageModels.json' }]) {
    const f = fixture(t, options); await f.start(); assert.equal(f.errors.length, 1);
    assert.equal(f.stats.launched + f.stats.bridges + f.stats.dialogs, 0);
  }
});
test('each partial write, including a write-before-rejection, rolls back owned state', async t => {
  for (const failedAt of [1, 2, 3]) for (const writeBeforeReject of [false, true]) {
    const f = fixture(t, { writeBeforeReject, writeFailure: (key, value, n) => n === failedAt });
    await f.start(); assert.equal(f.stats.stopped, 1); assert.ok(f.stats.closed >= 1);
    assert.deepEqual(f.values.remoteAgentHosts || [], []);
    assert.equal(f.values.remoteAgentHostsEnabled, undefined); assert.equal(f.values.remoteAgentHostsAutoConnect, undefined);
    assert.match(f.errors[0], /during Remote Host settings registration/); assert.ok(!f.errors[0].includes('secret'));
    await f.stop(); assert.equal(f.stats.stopped, 1);
  }
});
test('cleanup failures preserve the original error and retain an explicit retry handle', async t => {
  let failing = true;
  const f = fixture(t, { stopFailure: () => failing, closeFailure: () => failing,
    writeFailure: (key, value, n) => n === 2 || (failing && key === 'remoteAgentHosts' && n > 2) });
  await f.start(); assert.match(f.errors[0], /during Remote Host settings registration.*Cleanup incomplete/);
  assert.ok(!f.errors[0].includes('secret')); assert.equal(f.stats.stopped, 1); assert.equal(f.stats.closed, 1);
  await f.start(); assert.equal(f.stats.launched, 1);
  failing = false; await f.stop(); assert.equal(f.stats.stopped, 2); assert.deepEqual(f.values.remoteAgentHosts, []);
  await f.stop(); assert.equal(f.stats.stopped, 2);
});
test('repeated Start/Stop and deactivate are serialized and idempotent', async t => {
  let resume; const waitLaunch = new Promise(resolve => { resume = resolve; }); const f = fixture(t, { waitLaunch });
  const first = f.start(), second = f.start(), stop = f.stop(); resume(); await Promise.all([first, second, stop]);
  assert.equal(f.stats.launched, 1); assert.equal(f.stats.stopped, 1); await f.stop(); await f.deactivate();
  assert.equal(f.stats.stopped, 1); await f.start(); assert.equal(f.stats.launched, 2); await f.deactivate();
  assert.equal(f.stats.stopped, 2);
});
test('other registrations, tokens and enablement survive partial failure and Stop', async t => {
  const other = { name: 'Other', address: 'ws://127.0.0.1:20000/other', connectionToken: 'synthetic' };
  const f = fixture(t, { values: { remoteAgentHosts: [other] } }); await f.start();
  const concurrent = { name: f.owned.name, address: 'ws://127.0.0.1:20001/other' };
  f.values.remoteAgentHosts.push(concurrent); await f.stop();
  assert.deepEqual(f.values.remoteAgentHosts, [other, concurrent]); assert.equal(f.values.remoteAgentHostsEnabled, true);
  const failed = fixture(t, { values: { remoteAgentHosts: [other] }, writeFailure: (key, value, n) => n === 3 });
  await failed.start(); assert.deepEqual(failed.values.remoteAgentHosts, [other]); assert.equal(failed.stats.stopped, 1);
});
test('a stale matching registration is preserved and only the new owned Host is stopped', async t => {
  const stale = { name: 'FRAG · 12345678', address: 'ws://127.0.0.1:20002/api/agents/ahp' };
  const f = fixture(t, { values: { remoteAgentHosts: [stale] } }); await f.start();
  assert.match(f.errors[0], /already registered/); assert.deepEqual(f.values.remoteAgentHosts, [stale]);
  assert.equal(f.updates.length, 0); assert.equal(f.stats.stopped, 1);
});
test('cancel, bridge failure and owned startup cleanup failure do not leak command rejections', async t => {
  const cancelled = fixture(t, { cancel: true }); await cancelled.start(); assert.equal(cancelled.stats.bridges, 0);
  const bridge = fixture(t, { bridgeFailure: true }); await bridge.start(); assert.equal(bridge.stats.launched, 0);
  let failing = true;
  const host = fixture(t, { launchFailure: true, failedOwnedHost: true, stopFailure: () => failing }); await host.start();
  assert.match(host.errors[0], /installed Host startup.*Cleanup incomplete/); failing = false; await host.stop();
  assert.equal(host.stats.stopped, 2);
});
test('configure preserves other opt-ins and uses native same-instance Agents handoff', async t => {
  const f = fixture(t, { choice: 'Open Agents' }); await f.configure();
  assert.equal(f.updates[0].value['other.extension'], true); assert.equal(f.updates[0].value['frag-local.frag-bridge'], true);
  assert.ok(f.info.includes('workbench.action.openAgentsWindow')); assert.equal(f.stats.launched + f.stats.bridges, 0);
});
test('pending native notifications do not block Stop or a cleanup retry', async t => {
  const f = fixture(t, { pendingNotification: true }); await f.start(); await f.start(); await f.stop();
  assert.equal(f.stats.stopped, 1);
  const failed = fixture(t, { pendingNotification: true, writeFailure: (key, value, n) => n === 2 });
  await failed.start(); await failed.stop(); assert.equal(failed.stats.stopped, 1);
});
test('bridge-only cleanup failure is retained without starting a replacement Host', async t => {
  let failing = true;
  const f = fixture(t, { launchFailure: true, closeFailure: () => failing }); await f.start();
  assert.match(f.errors[0], /installed Host startup.*owned model bridge shutdown/);
  await f.start(); assert.equal(f.stats.launched, 1); assert.equal(f.stats.bridges, 1);
  failing = false; await f.stop(); assert.equal(f.stats.closed, 2); assert.equal(f.stats.stopped, 0);
});
