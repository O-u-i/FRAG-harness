'use strict';
const vscode = require('vscode');
const { join, basename, resolve } = require('node:path');
const { realpathSync } = require('node:fs');
const { startBridge } = require('./model-bridge.cjs');
const { launchHost } = require('./host-launcher.cjs');
let host, pending = Promise.resolve();
const serial = action => (pending = pending.then(action, action));
const fail = message => { const error = new Error(message); error.fragMessage = message; throw error; };
const registered = (settings, key) => settings.inspect(key)?.defaultValue !== undefined;
function preflight(context) {
  if (process.platform !== 'win32' || vscode.env.appHost !== 'desktop' || vscode.env.remoteName
      || !['file', 'vscode-userdata'].includes(context.globalStorageUri.scheme)) {
    fail('FRAG requires a local Windows VS Code extension host. No process was started.');
  }
  const chat = vscode.workspace.getConfiguration('chat');
  const keys = ['remoteAgentHosts', 'remoteAgentHostsEnabled', 'remoteAgentHostsAutoConnect'];
  const missing = keys.filter(key => !registered(chat, key));
  if (missing.length) fail(`This window has no registered chat.${missing[0]} setting. Start FRAG in the Agents window of your dedicated isolated instance. No process was started.`);
  if (!Array.isArray(chat.get('remoteAgentHosts'))) fail('Remote Host settings must be an array. No process was started.');
  if (!vscode.workspace.isTrusted) fail('Trust this workspace before starting FRAG. No process was started.');
  // In 1.140.0 the internal Agents profile shares this instance's User resources.
  // A named editor profile is not the Agents profile. Never fall back to APPDATA.
  const configured = vscode.workspace.getConfiguration('frag').get('modelConfigFile');
  const expected = resolve(context.globalStorageUri.fsPath, '..', '..', 'chatLanguageModels.json');
  if (!configured || resolve(configured).toLowerCase() !== expected.toLowerCase()) {
    fail('Set frag.modelConfigFile explicitly to the dedicated Agents instance\'s User/chatLanguageModels.json. Named editor profiles are not used by Agents in VS Code 1.140.0. See MODEL-CONFIGURATION.md. No process was started.');
  }
  try {
    if (realpathSync(configured).toLowerCase() !== expected.toLowerCase()) throw new Error('Linked model configuration');
  } catch { fail('The dedicated model configuration is missing or linked. Open Chat: Open Language Models (JSON) in Agents and save it before starting. No process was started.'); }
  return configured;
}
async function registerHost(value) {
  const chat = vscode.workspace.getConfiguration('chat');
  // Journal before each write: a rejected write may already have changed the file.
  const entries = chat.get('remoteAgentHosts');
  if (!Array.isArray(entries)) fail('Remote Host settings changed to a non-array.');
  if (entries.some(row => row?.name === value.name || row?.address === value.address)) {
    fail('A matching Remote Host is already registered. Inspect it manually before restarting; FRAG did not replace it.');
  }
  value.registration = { touched: true, flags: [] };
  await chat.update('remoteAgentHosts', [...entries, { name: value.name, address: value.address }], vscode.ConfigurationTarget.Global);
  for (const key of ['remoteAgentHostsEnabled', 'remoteAgentHostsAutoConnect']) {
    if (chat.get(key) === true) continue;
    value.registration.flags.push({ key, previous: chat.inspect(key)?.globalValue });
    await chat.update(key, true, vscode.ConfigurationTarget.Global);
  }
}
async function cleanup(value) {
  if (!value) return [];
  const issues = [];
  // Independent cleanup attempts; a settings failure never prevents owned shutdown.
  try { await value.stop(); } catch { issues.push('owned Host shutdown'); }
  try { await value.bridge?.close(); } catch { issues.push('owned model bridge shutdown'); }
  if (!value.registration?.touched) return issues;
  const chat = vscode.workspace.getConfiguration('chat');
  try {
    const entries = chat.get('remoteAgentHosts');
    if (!Array.isArray(entries)) throw new Error('Invalid settings');
    const remaining = entries.filter(row => !(row?.name === value.name && row?.address === value.address));
    if (remaining.length !== entries.length) {
      await chat.update('remoteAgentHosts', remaining, vscode.ConfigurationTarget.Global);
    }
    // Restore our flags only when there are no other consumers. Never undo another host's enablement.
    if (remaining.length === 0) for (const { key, previous } of [...value.registration.flags].reverse()) {
      try {
        if (chat.get(key) === true) await chat.update(key, previous, vscode.ConfigurationTarget.Global);
      } catch { issues.push(`chat.${key} restoration`); }
    }
  } catch { issues.push('Remote Host registration removal'); }
  return issues;
}
async function stop(notify = true) {
  const issues = await cleanup(host);
  // Retain the owned handle for an explicit Stop retry after incomplete cleanup.
  if (!issues.length) host = undefined;
  if (notify && issues.length) vscode.window.showErrorMessage(`FRAG cleanup incomplete: ${issues.join(', ')}. Retry FRAG: Stop Project Host; inspect the stale FRAG entry manually if settings remain unavailable.`);
  return issues;
}
async function start(context) {
  if (host) { vscode.window.showInformationMessage('FRAG already owns a Host or pending cleanup. Run FRAG: Stop Project Host before starting another.'); return; }
  let bridge, stage = 'environment validation';
  try {
    const configFile = preflight(context);
    const chosen = await vscode.window.showOpenDialog({ canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
      title: 'Choose FRAG evidence project', openLabel: 'Bind project', defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri });
    if (!chosen?.length) return;
    if (chosen[0].scheme !== 'file') fail('Choose a local Windows folder.');
    const settings = vscode.workspace.getConfiguration('frag');
    const installation = settings.get('hostInstallation') || join(process.env.LOCALAPPDATA, 'FRAG', 'host', '1.10.0');
    stage = 'dedicated model configuration';
    bridge = await startBridge(vscode, configFile);
    stage = 'installed Host startup';
    host = await launchHost(installation, chosen[0].fsPath, context.globalStorageUri.fsPath, bridge);
    stage = 'Remote Host settings registration';
    await registerHost(host);
    // Notifications must not hold the lifecycle queue while waiting for a click.
    vscode.window.showInformationMessage(
      `${basename(host.project)} is bound to ${host.name}. In Agents: New → folder-name button → Remote → ${host.name} → Folders.`, 'Open Review')
      .then(choice => { if (choice === 'Open Review') return review(); })
      .catch(() => vscode.window.showErrorMessage('Open FRAG Review manually from the Agents command palette.'));
  } catch (error) {
    if (!host && error.ownedHost) host = error.ownedHost;
    let issues;
    if (host) issues = await stop(false);
    else {
      issues = [];
      try { await bridge?.close(); } catch {
        issues.push('owned model bridge shutdown');
        host = { bridge, async stop() {} }; // Keep bridge-only cleanup retryable too.
      }
    }
    // Only controlled diagnostics reach the UI; provider/configuration errors can contain secrets.
    const original = error.fragMessage || `FRAG could not start during ${stage}. See the integration README.`;
    vscode.window.showErrorMessage(original + (issues.length ? ` Cleanup incomplete: ${issues.join(', ')}. Retry Stop; the owned handle was retained.` : ''));
  }
}
async function review() {
  let origin = host?.origin;
  if (!origin) {
    const entries = vscode.workspace.getConfiguration('chat').get('remoteAgentHosts', []);
    const candidates = Array.isArray(entries) ? entries.filter(row => typeof row.name === 'string' && /^FRAG · [a-f0-9]{8}$/.test(row.name)
      && /^ws:\/\/127\.0\.0\.1:\d+\/api\/agents\/ahp$/.test(row.address)) : [];
    const chosen = candidates.length === 1 ? candidates[0] : await vscode.window.showQuickPick(candidates.map(row => ({ label: row.name, address: row.address })), { title: 'Choose running FRAG Host' });
    if (chosen) origin = chosen.address.replace('ws:', 'http:').replace('/api/agents/ahp', '');
  }
  if (!origin) return vscode.window.showInformationMessage('Run FRAG: Start Project Host first.');
  // The native Browser action has no URL argument. Clipboard + explicit navigation avoids private APIs.
  await vscode.env.clipboard.writeText(origin + '/review');
  const commands = await vscode.commands.getCommands(true);
  if (commands.includes('workbench.action.agentSessions.newBrowserTab')) {
    await vscode.commands.executeCommand('workbench.action.agentSessions.newBrowserTab');
  }
  vscode.window.showInformationMessage('FRAG Review URL copied. In the Agents right-hand Browser, paste it into the address bar and select your FRAG session.');
}
function activate(context) {
  const command = (id, action) => context.subscriptions.push(vscode.commands.registerCommand(id, action));
  command('frag.start', () => serial(() => start(context)));
  command('frag.stop', () => serial(() => stop()));
  command('frag.review', review);
  command('frag.configure', async () => {
    const settings = vscode.workspace.getConfiguration('extensions');
    try {
      if (!registered(settings, 'supportAgentsWindow')) fail('This window does not register extensions.supportAgentsWindow. Use the dedicated isolated desktop instance.');
      await settings.update('supportAgentsWindow', { ...settings.get('supportAgentsWindow', {}), 'frag-local.frag-bridge': true }, vscode.ConfigurationTarget.Global);
      const choice = await vscode.window.showInformationMessage('FRAG opt-in saved. VS Code 1.140.0 Agents uses this instance\'s Default extensions/settings/models, even with --profile. Install the VSIX in the dedicated instance without --profile, then reload Agents. No models or keys were copied.', 'Open Agents');
      if (choice === 'Open Agents') await vscode.commands.executeCommand('workbench.action.openAgentsWindow');
    } catch (error) { await vscode.window.showErrorMessage(error.fragMessage || 'FRAG could not save the Agents opt-in or open its window. Use the dedicated instance and reload Agents manually.'); }
  });
}
function deactivate() { return serial(() => stop(false)); }
module.exports = { activate, deactivate };
