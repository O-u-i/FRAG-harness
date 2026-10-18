'use strict';
const { spawn } = require('node:child_process');
const { realpathSync, existsSync, mkdirSync, readFileSync } = require('node:fs');
const { join } = require('node:path');
const { createHash, randomBytes } = require('node:crypto');
const net = require('node:net');
const VERSION = '1.13.2';
function projectIdentity(folder) { return createHash('sha256').update(realpathSync(folder).toLowerCase()).digest('hex'); }
async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve)); return port;
}
function hostEnvironment(installation, token, source = process.env) {
  const env = {};
  for (const name of ['PATH','Path','SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','COMSPEC']) if (source[name]) env[name] = source[name];
  return { ...env, PYTHONPATH: join(installation, 'backend'), PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1', FRAG_EXTENSION_TOKEN: token };
}
async function stopChild(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === 'win32') await new Promise((resolve, reject) => {
    const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    killer.once('error', reject); killer.once('exit', code => code === 0 || child.exitCode !== null ? resolve() : reject(new Error('Owned backend termination failed')));
  }); else child.kill();
}
async function launchHost(installation, folder, storage) {
  const project = realpathSync(folder), id = projectIdentity(project);
  const python = join(installation, 'backend', '.venv', 'Scripts', 'python.exe');
  if (!existsSync(python) || !existsSync(join(installation, 'resources', 'dist', 'index.html')) ||
      !readFileSync(join(installation, 'backend', 'pyproject.toml'), 'utf8').includes(`version = "${VERSION}"`)) {
    throw new Error(`Install and initialize the matching v${VERSION} backend bundle.`);
  }
  const state = join(storage, 'projects', id); mkdirSync(state, { recursive: true });
  const port = await unusedPort(), token = randomBytes(32).toString('hex');
  const child = spawn(python, ['-X','utf8','-m','frag_api.host','--installation',installation,'--workspace',project,'--state-dir',state,'--port',String(port)], {
    cwd: installation, env: hostEnvironment(installation, token), windowsHide: true, stdio: 'ignore',
  });
  let failed = false; child.on('error', () => { failed = true; }); child.on('exit', () => { failed = true; });
  const origin = `http://127.0.0.1:${port}`;
  const owned = { child, project, id, state, installation, origin, async stop() { await stopChild(child); },
    async request(path, body, signal) {
      const response = await fetch(origin + path, { method: body === undefined ? 'GET' : 'POST',
        headers: { authorization: 'Bearer ' + token, 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120000)]) : AbortSignal.timeout(120000), redirect: 'error' });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error?.code || 'LOCAL_OPERATION_FAILED');
      return value;
    } };
  try {
    for (let i = 0; i < 200; i++) {
      if (failed) throw new Error('Backend startup failed. Check matching version, separate directories and duplicate project windows.');
      try { const health = await owned.request('/api/health', undefined, AbortSignal.timeout(400));
        if (health.service === 'frag-harness' && health.serviceVersion === VERSION) return owned;
      } catch { /* Only startup health is retried, never a tool call. */ }
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw new Error('Backend startup timed out.');
  } catch (error) { await owned.stop(); throw error; }
}
module.exports = { launchHost, hostEnvironment, projectIdentity, stopChild };
