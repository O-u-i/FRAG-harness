'use strict';
const vscode = require('vscode');
const { join, basename } = require('node:path');
const { startBridge } = require('./model-bridge.cjs');
const { launchHost } = require('./host-launcher.cjs');
let host, starting = false;

async function registerHost(value) {
  const chat = vscode.workspace.getConfiguration('chat');
  const entries = chat.get('remoteAgentHosts', []);
  if (!Array.isArray(entries)) throw new Error('Remote Host settings must be an array.');
  await chat.update('remoteAgentHosts', [...entries.filter(row => row.name !== value.name),
    { name: value.name, address: value.address }], vscode.ConfigurationTarget.Global);
  await chat.update('remoteAgentHostsEnabled', true, vscode.ConfigurationTarget.Global);
  await chat.update('remoteAgentHostsAutoConnect', true, vscode.ConfigurationTarget.Global);
}
async function stop() {
  const value = host;
  if (!value) return;
  host = undefined;
  value.stop();
  const chat = vscode.workspace.getConfiguration('chat');
  const entries = chat.get('remoteAgentHosts', []);
  if (Array.isArray(entries)) await chat.update('remoteAgentHosts', entries.filter(row => row.address !== value.address), vscode.ConfigurationTarget.Global);
}
async function start(context) {
  if (starting) return;
  starting = true;
  let bridge;
  try {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before starting FRAG.');
    const chosen = await vscode.window.showOpenDialog({ canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
      title: 'Choose FRAG evidence project', openLabel: 'Bind project', defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri });
    if (!chosen?.length) return;
    if (chosen[0].scheme !== 'file') throw new Error('Choose a local Windows folder.');
    await stop();
    const settings = vscode.workspace.getConfiguration('frag');
    const installation = settings.get('hostInstallation') || join(process.env.LOCALAPPDATA, 'FRAG', 'host', '1.10.0');
    const configFile = settings.get('modelConfigFile') || join(process.env.APPDATA, 'Code', 'User', 'chatLanguageModels.json');
    bridge = await startBridge(vscode, configFile);
    host = await launchHost(installation, chosen[0].fsPath, context.globalStorageUri.fsPath, bridge);
    await registerHost(host);
    const choice = await vscode.window.showInformationMessage(
      `${basename(host.project)} is bound to ${host.name}. In Agents: New → folder-name button → Remote → ${host.name} → Folders.`, 'Open Agents', 'Open Review');
    if (choice === 'Open Agents') {
      const { spawn } = require('node:child_process');
      const env = { ...process.env }; delete env.ELECTRON_RUN_AS_NODE;
      const launcher = spawn(process.execPath, ['--agents'], { env, detached: true, stdio: 'ignore', windowsHide: true });
      launcher.on('error', () => vscode.window.showErrorMessage('Open the Agents window from VS Code to continue.'));
      launcher.unref();
    } else if (choice === 'Open Review') await review();
  } catch {
    if (host) await stop(); else bridge?.close();
    vscode.window.showErrorMessage('FRAG could not start. Check Host installation, active model configuration, and model API access. See the integration README.');
  } finally { starting = false; }
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
  command('frag.start', () => start(context));
  command('frag.stop', stop);
  command('frag.review', review);
  command('frag.configure', async () => {
    const settings = vscode.workspace.getConfiguration('extensions');
    await settings.update('supportAgentsWindow', { ...settings.get('supportAgentsWindow', {}), 'frag-local.frag-bridge': true }, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage('FRAG enabled for the Agents window. Reload that window, then run FRAG: Start Project Host.');
  });
}
function deactivate() { return stop(); }
module.exports = { activate, deactivate };
