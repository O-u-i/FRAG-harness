import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer, isFileServingAllowed, loadConfigFromFile, normalizePath } from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
const maintenance = join(root, 'scripts', 'maintain-tmp.ps1');
const maintain = (...args) => execFileSync('pwsh', ['-NoProfile', '-File', maintenance, ...args], {
  cwd: root, encoding: 'utf8', windowsHide: true,
});

test('Vite serves public UI only and refuses private/outside paths and query bypasses', { timeout: 120_000 }, async t => {
  const inventory = JSON.parse(maintain());
  assert.equal(inventory.aboveCeiling, false, 'Temporary storage must be below the policy ceiling.');
  const run = maintain('-NewRun', 'dev-server-boundary', '-Disposable', '-OwnerProcessId', String(process.pid)).trim();
  t.diagnostic(`Synthetic fixtures: ${run}`);
  let server;
  try {
    const loaded = await loadConfigFromFile({ command: 'serve', mode: 'test' },
      join(root, 'vite.config.ts'), root, 'silent', undefined, 'runner');
    assert.ok(loaded, 'Load the actual repository Vite configuration.');
    const configured = loaded.config;
    assert.equal(configured.server.host, '127.0.0.1');
    assert.equal(configured.server.fs.strict, true);
    assert.equal(configured.publicDir, false);
    const expectedAllow = ['src', 'node_modules', 'index.html'].map(name => normalizePath(resolve(root, name))).sort();
    assert.deepEqual(configured.server.fs.allow.map(normalizePath).sort(), expectedAllow);

    const sentinel = 'synthetic-private-dev-server-sentinel';
    const fixtures = ['.local-guidance/note.md', 'local-sources/note.md', 'backend/note.py',
      'outside/note.md', 'private/note space.md', '.env', 'runtime.sqlite3', 'AGENTS.md'];
    for (const name of fixtures) {
      const file = join(run, name);
      await mkdir(resolve(file, '..'), { recursive: true });
      await writeFile(file, sentinel, 'utf8');
    }

    // The real .tmp deny remains intact, so public requests use tracked UI files.
    // All private HTTP fixtures are synthetic; no actual state, vault or .env is read.
    server = await createServer({
      ...configured, configFile: false, root, mode: 'test', envFile: false, logLevel: 'silent',
      cacheDir: join(run, 'vite-cache'),
      optimizeDeps: { noDiscovery: true, entries: [], include: [] },
      server: { ...configured.server, port: 0, strictPort: true, hmr: false, watch: null,
        preTransformRequests: false, fs: { ...configured.server.fs, allow: [...configured.server.fs.allow] } },
    });
    assert.equal(server.config.server.host, '127.0.0.1');
    assert.equal(server.config.server.fs.strict, true);
    assert.deepEqual(server.config.server.fs.deny, configured.server.fs.deny);
    await server.listen();
    const address = server.httpServer.address();
    assert.ok(address && typeof address === 'object');
    assert.equal(address.address, '127.0.0.1');
    const origin = `http://127.0.0.1:${address.port}`;
    for (const path of ['/index.html', '/src/management/client.ts']) {
      const response = await fetch(origin + path);
      assert.equal(response.status, 200, `Public UI must remain accessible: ${path}`);
      assert.ok((await response.text()).length);
    }

    const denied = new Map();
    for (const name of fixtures) {
      const file = join(run, name);
      const direct = '/' + normalizePath(relative(root, file));
      const absolute = '/@fs/' + normalizePath(file);
      for (const path of [direct, absolute]) {
        denied.set(path, [403]);
        denied.set(path + '?raw', [403]);
        denied.set(path + '?url&import', [403]);
        // Encoded directory separators/names may not resolve to an existing file.
        // Use a non-HTML Accept so missing paths cannot become the public SPA.
        denied.set(path.replaceAll('note', '%6Eote'), [403, 404]);
        denied.set(path.replaceAll('+', '%2B').replaceAll('note', '%6Eote'), [403, 404]);
      }
      // A space becomes %20 but still names an existing synthetic private file.
      denied.set(new URL(direct, origin).pathname, [403]);
      denied.set(new URL(absolute, origin).pathname, [403]);
    }
    for (const [path, statuses] of denied) {
      const response = await fetch(origin + path, { redirect: 'manual', headers: { accept: 'application/octet-stream' } });
      const body = await response.text();
      assert.ok(statuses.includes(response.status), `Private path must be refused: ${path} (${response.status})`);
      assert.equal(body.includes(sentinel), false, 'A refusal must not contain private bytes.');
    }
    // Pure predicates cover each root-level category without opening real private files.
    for (const name of fixtures) {
      assert.equal(isFileServingAllowed(server.config, '/@fs/' + normalizePath(join(root, name))), false,
        `Root-level private/outside category must be denied: ${name}`);
    }
  } finally {
    try { if (server) await server.close(); }
    finally { maintain('-CloseRun', run); }
  }
});
