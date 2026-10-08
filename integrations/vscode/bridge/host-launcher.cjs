'use strict';
const { spawn } = require('node:child_process');
const { realpathSync, existsSync, mkdirSync } = require('node:fs');
const { join } = require('node:path');
const { createHash } = require('node:crypto');
const net = require('node:net');

function projectIdentity(folder) {
  return createHash('sha256').update(realpathSync(folder).toLowerCase()).digest('hex');
}
async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
function hostEnvironment(installation, key, source = process.env) {
  const env = {};
  for (const name of ['PATH', 'Path', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC']) {
    if (source[name]) env[name] = source[name];
  }
  return { ...env, PYTHONPATH: join(installation, 'backend'), PYTHONUTF8: '1',
    PYTHONDONTWRITEBYTECODE: '1', FRAG_HOST_INSTALLED: '1', FRAG_BRIDGE_KEY: key };
}
async function stopChild(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  // Windows venv launchers can own a second Python process. Stop this owned tree only.
  if (process.platform === 'win32') {
    await new Promise((resolve, reject) => {
      const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      killer.once('error', reject);
      killer.once('exit', code => code === 0 || child.exitCode !== null || child.signalCode !== null
        ? resolve() : reject(new Error('Owned Host termination failed')));
    });
  } else child.kill();
  if (child.exitCode === null && child.signalCode === null) await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { child.removeListener('exit', done); reject(new Error('Owned Host termination timed out')); }, 5000);
    function done() { clearTimeout(timer); resolve(); }
    child.once('exit', done);
  });
}
async function launchHost(installation, folder, storage, bridge) {
  const project = realpathSync(folder), id = projectIdentity(project);
  const python = join(installation, 'backend', '.venv', 'Scripts', 'python.exe');
  if (!existsSync(python) || !existsSync(join(installation, 'resources', 'dist', 'index.html'))) {
    throw new Error('Install and initialize the v1.10.3 Host bundle before starting.');
  }
  const state = join(storage, 'projects', id);
  mkdirSync(state, { recursive: true });
  const port = await unusedPort();
  const child = spawn(python, ['-X', 'utf8', '-m', 'frag_api.host', '--installation', installation,
    '--workspace', project, '--state-dir', state, '--port', String(port), '--bridge-url', bridge.address,
    '--preferences-path', join(storage, 'review-preferences.sqlite3')], {
    cwd: installation, env: hostEnvironment(installation, bridge.key), windowsHide: true, stdio: 'ignore',
  });
  let failed = false;
  child.on('error', () => { failed = true; });
  child.on('exit', () => { failed = true; });
  const origin = `http://127.0.0.1:${port}`;
  const owned = { child, bridge, project, id, origin, address: `ws://127.0.0.1:${port}/api/agents/ahp`,
    name: `FRAG · ${id.slice(0, 8)}`, async stop() { try { await stopChild(child); } finally { await bridge.close(); } } };
  try {
    for (let attempt = 0; attempt < 200; attempt++) {
      if (failed) throw new Error('Host startup failed. Check the installed bundle and directory separation.');
      try {
        const response = await fetch(origin + '/api/health', { signal: AbortSignal.timeout(400), redirect: 'error' });
        const value = await response.json();
        if (response.ok && value.service === 'frag-harness' && value.serviceVersion === '1.10.3') {
          return owned;
        }
      } catch { /* A bound process may still be starting. Poll health only; never poll a model call. */ }
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw new Error('Host did not become ready.');
  } catch (error) {
    try { await owned.stop(); } catch { error.ownedHost = owned; }
    throw error;
  }
}
module.exports = { launchHost, hostEnvironment, projectIdentity };
