'use strict';
const vscode = require('vscode');
const { join } = require('node:path');
const { readFileSync } = require('node:fs');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { launchHost } = require('./host-launcher.cjs');
const { canonical, fitPack } = require('./tool-result.cjs');
const { workspaceInfo, prepareWorkspace } = require('./acceptance-workspace.cjs');
const WORKSPACE_ACTIONS = new Set(['workspace-info','workspace-prepare','workspace-open','workspace-pick']);
const LOCAL_ACTIONS = new Set([...WORKSPACE_ACTIONS, 'ui-preferences-read','ui-preferences-save','settings-open','state-open','locations-info']);
const ACTIONS = new Set(['overview','run-get','source-save','source-status','source-build','plan-confirm','fc-connection-open','fc-connection-check','memory-candidate','memory-revise','memory-promote','memory-retire','memory-versions','memory-conflict','memory-resolve','memory-recommend', ...LOCAL_ACTIONS]);
const PREFERENCE_KEY = 'frag.presentation.v1';
const PREFERENCE_DEFAULTS = { theme: 'system', density: 'compact', motion: true, runLimit: 50, advanced: false };
function normalizePreferences(value, strict = false) {
  const input = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  if (strict && (Object.keys(input).sort().join(',') !== Object.keys(PREFERENCE_DEFAULTS).sort().join(',') ||
      !['system','dracula','living'].includes(input.theme) || !['compact','comfortable'].includes(input.density) ||
      typeof input.motion !== 'boolean' || ![25,50,100,200].includes(input.runLimit) || typeof input.advanced !== 'boolean')) throw new Error('UI_PREFERENCES_INVALID');
  return { theme: ['system','dracula','living'].includes(input.theme) ? input.theme : PREFERENCE_DEFAULTS.theme,
    density: ['compact','comfortable'].includes(input.density) ? input.density : PREFERENCE_DEFAULTS.density,
    motion: typeof input.motion === 'boolean' ? input.motion : PREFERENCE_DEFAULTS.motion,
    runLimit: [25,50,100,200].includes(input.runLimit) ? input.runLimit : PREFERENCE_DEFAULTS.runLimit,
    advanced: typeof input.advanced === 'boolean' ? input.advanced : PREFERENCE_DEFAULTS.advanced };
}
let host, starting, panel;
function activate(context) {
  async function start() {
    if (host && host.child.exitCode === null && host.child.signalCode === null) return host;
    if (starting) return starting;
    if (!vscode.workspace.isTrusted || vscode.env.remoteName || vscode.workspace.workspaceFolders?.length !== 1 || vscode.workspace.workspaceFolders[0].uri.scheme !== 'file') {
      throw new Error('FRAG requires one trusted local desktop workspace.');
    }
    const installation = vscode.workspace.getConfiguration('frag').get('hostInstallation') || join(process.env.LOCALAPPDATA, 'FRAG', 'host', '1.14.0');
    const storage = vscode.workspace.getConfiguration('frag').get('privateStateRoot') || context.globalStorageUri.fsPath;
    starting = launchHost(installation, vscode.workspace.workspaceFolders[0].uri.fsPath, storage);
    try { host = await starting; return host; } finally { starting = undefined; }
  }
  async function stop() {
    if (starting) await starting.catch(() => {});
    if (host) { await host.stop(); host = undefined; }
  }
  async function connectFC() {
    const owned = await start();
    await owned.request('/api/manage/fc-connection-prepare', {});
    const windows = process.env.SystemRoot || process.env.WINDIR;
    if (!windows) throw new Error('FC_PRIVATE_EDITOR_UNAVAILABLE');
    await new Promise((resolve, reject) => {
      const editor = spawn(join(windows, 'System32', 'notepad.exe'), [join(owned.state, 'fc.env')], { windowsHide: false, stdio: 'ignore' });
      editor.once('error', () => reject(new Error('FC_PRIVATE_EDITOR_UNAVAILABLE')));
      editor.once('spawn', () => { editor.unref(); resolve(); });
    });
    void vscode.window.showInformationMessage('Paste the FC connection configuration in Notepad: Ctrl+A, Ctrl+V, Ctrl+S. Then use Check connection in FRAG Settings.').then(undefined, () => {});
    return { opened: true };
  }
  async function acceptanceWorkspace(action, body = {}) {
    try {
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).some(key => action !== 'workspace-open' || key !== 'target') ||
          (body.target !== undefined && !['root','plan'].includes(body.target))) throw new Error('ACCEPTANCE_REQUEST_INVALID');
      const owned = await start(), config = vscode.workspace.getConfiguration('frag');
      let root = config.get('acceptanceRoot') || '';
      if (action === 'workspace-pick') {
        const selected = await vscode.window.showOpenDialog({ canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
          title: 'Choose a private synthetic acceptance container', openLabel: 'Use acceptance container' });
        if (selected?.length) {
          if (selected.length !== 1 || selected[0].scheme !== 'file') throw new Error('ACCEPTANCE_ROOT_INVALID');
          root = selected[0].fsPath;
          workspaceInfo(owned, root); // Validate before persisting a machine-local setting.
          await config.update('acceptanceRoot', root, vscode.ConfigurationTarget.Global);
        }
      }
      const info = action === 'workspace-prepare' ? prepareWorkspace(owned, root) : workspaceInfo(owned, root);
      if (action === 'workspace-open') {
        if (!info.prepared) throw new Error('ACCEPTANCE_NOT_PREPARED');
        if (body.target === 'plan') await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(vscode.Uri.file(info.planPath)), { preview: false });
        else if (!await vscode.env.openExternal(vscode.Uri.file(info.root))) throw new Error('ACCEPTANCE_FOLDER_OPEN_FAILED');
      }
      return info;
    } catch (error) {
      // Do not forward OS errors or file content into the Webview.
      throw new Error(/^ACCEPTANCE_[A-Z_]+$/.test(error?.message || '') ? error.message : 'ACCEPTANCE_OPERATION_FAILED');
    }
  }
  async function localAction(action, body = {}) {
    if (WORKSPACE_ACTIONS.has(action)) return acceptanceWorkspace(action, body);
    if (action === 'ui-preferences-save') {
      const value = normalizePreferences(body, true);
      if (!context.globalState?.update) throw new Error('UI_PREFERENCES_UNAVAILABLE');
      try { await context.globalState.update(PREFERENCE_KEY, value); } catch { throw new Error('UI_PREFERENCES_SAVE_FAILED'); }
      return value;
    }
    if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length) throw new Error('UI_PREFERENCES_INVALID');
    if (action === 'ui-preferences-read') return normalizePreferences(context.globalState?.get(PREFERENCE_KEY));
    if (action === 'settings-open') {
      try { await vscode.commands.executeCommand('workbench.action.openSettings', 'frag'); } catch { throw new Error('SETTINGS_OPEN_FAILED'); }
      return { opened: true };
    }
    if (action === 'state-open') {
      const owned = await start();
      if (!await vscode.env.openExternal(vscode.Uri.file(owned.state))) throw new Error('FRAG_PRIVATE_STATE_FOLDER_OPEN_FAILED');
      return { opened: true };
    }
    if (action === 'locations-info') {
      const owned = await start(), workspace = await acceptanceWorkspace('workspace-info');
      return { stateRoot: owned.state, hostRoot: owned.installation, acceptanceRoot: workspace.root, sourceRoot: workspace.sourceRoot, planPath: workspace.planPath };
    }
    throw new Error('LOCAL_ACTION_INVALID');
  }
  context.subscriptions.push({ dispose() { void stop(); } });
  for (const name of ['frag_search','frag_read','frag_fc_read']) {
    context.subscriptions.push(vscode.lm.registerTool(name, {
      prepareInvocation() { return { invocationMessage: 'Reading authorized FRAG evidence' }; },
      async invoke(options, cancellation) {
        const owned = await start();
        if (cancellation.isCancellationRequested) throw new vscode.CancellationError();
        const abort = new AbortController();
        const listener = cancellation.onCancellationRequested(() => abort.abort());
        let pack;
        try {
          pack = await owned.request('/api/tools/' + name, options.input, abort.signal);
          const fitted = await fitPack(pack, options.tokenizationOptions, cancellation);
          if (cancellation.isCancellationRequested) throw new vscode.CancellationError();
          const result = await owned.request('/api/tools/complete', { runId: pack.runId, omittedEvidenceIds: fitted.omitted, tokenCount: fitted.tokens }, abort.signal);
          return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(canonical(result))]);
        } catch (error) {
          if (pack && !cancellation.isCancellationRequested) {
            await owned.request('/api/tools/complete', {runId: pack.runId, failure: error.message.includes('TOKEN_BUDGET') ? 'TOOL_TOKEN_BUDGET_TOO_SMALL' : 'TOOL_RESULT_FAILED'}).catch(() => {});
          }
          throw error;
        } finally {
          listener.dispose();
          if (pack && cancellation.isCancellationRequested) {
            await owned.request('/api/tools/complete', {runId: pack.runId, cancelled: true}).catch(() => {});
          }
          // UI delivery must never change a persisted tool's success/error outcome.
          try { if (panel) void panel.webview.postMessage({ type: 'runsChanged' }).then(undefined, () => {}); }
          catch { /* A closing Webview must not mask a tool result. */ }
        }
      },
    }));
  }
  async function open(page, sourceId = '', focusAcceptance = false) {
    const owned = await start();
    if (!panel) {
      panel = vscode.window.createWebviewPanel('frag.management', 'FRAG · 1.14.0', vscode.ViewColumn.Beside, {
        enableScripts: true, localResourceRoots: [vscode.Uri.file(join(owned.installation, 'resources', 'dist'))],
      });
      const webview = panel.webview, nonce = randomBytes(16).toString('hex');
      const base = webview.asWebviewUri(vscode.Uri.file(join(owned.installation,'resources','dist'))).toString();
      const html = readFileSync(join(owned.installation,'resources','dist','index.html'), 'utf8')
        .replace('</head>', '<script type="text/javascript">globalThis.FRAG_INITIAL_ACCEPTANCE=' + JSON.stringify(focusAcceptance) + ';</script></head>');
      webview.html = html.replace(/(src|href)="\.\/([^\"]+)"/g, (_, attr, path) => `${attr}="${base}/${path}"`)
        .replace(/<script /g, `<script nonce="${nonce}" `)
        .replace('<head>', `<head><script nonce="${nonce}">globalThis.FRAG_INITIAL_PAGE=${JSON.stringify(page)};globalThis.FRAG_INITIAL_SOURCE_ID=${JSON.stringify(sourceId)};</script><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src ${webview.cspSource}; img-src ${webview.cspSource} data:; font-src 'none'; connect-src 'none';">`);
      panel.onDidDispose(() => { panel = undefined; });
      webview.onDidReceiveMessage(async message => {
        if (!message || typeof message.id !== 'number' || !ACTIONS.has(message.action)) return;
        try { const value = LOCAL_ACTIONS.has(message.action) ? await localAction(message.action, message.body) : message.action === 'fc-connection-open' ? await connectFC() : await (await start()).request('/api/manage/' + message.action, message.body || {});
          await webview.postMessage({ id: message.id, value });
        } catch (error) { await webview.postMessage({ id: message.id, error: error.message }); }
      }, undefined, context.subscriptions);
    }
    panel.reveal(vscode.ViewColumn.Beside);
    await panel.webview.postMessage({ page, sourceId, focusAcceptance });
  }
  for (const page of ['settings','runs','memory']) context.subscriptions.push(vscode.commands.registerCommand('frag.' + page, () => open(page)));
  context.subscriptions.push(vscode.commands.registerCommand('frag.acceptance', () => open('settings', '', true)));
  context.subscriptions.push(vscode.commands.registerCommand('frag.start', start));
  context.subscriptions.push(vscode.commands.registerCommand('frag.stop', stop));
  context.subscriptions.push(vscode.commands.registerCommand('frag.connectFC', async () => { await open('settings', 'finance-core'); return connectFC(); }));
  context.subscriptions.push(vscode.commands.registerCommand('frag.openState', async () => {
    const owned = await start();
    if (!await vscode.env.openExternal(vscode.Uri.file(owned.state))) throw new Error('FRAG_PRIVATE_STATE_FOLDER_OPEN_FAILED');
  }));
  context.subscriptions.push(vscode.commands.registerCommand('frag.openFC', async () => {
    const url = vscode.workspace.getConfiguration('frag').get('financeCoreUI') || 'http://127.0.0.1:5174';
    const parsed = new URL(url);
    if (!['http:','https:'].includes(parsed.protocol) || !['127.0.0.1','localhost','[::1]'].includes(parsed.hostname) || parsed.username || parsed.password) throw new Error('Use a loopback Finance Core UI URL without credentials.');
    await vscode.env.openExternal(vscode.Uri.parse(parsed.toString()));
  }));
  return { start, stop };
}
module.exports = { activate };
