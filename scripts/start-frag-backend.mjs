import { spawn } from 'node:child_process';

const child = spawn('uv', [
  'run', '--project', 'backend', '--cache-dir', '.tmp/uv-cache',
  'uvicorn', 'frag_api.main:app', '--host', '127.0.0.1', '--port', '8787',
  '--reload', '--reload-dir', 'backend/frag_api',
], { stdio: 'inherit', windowsHide: true });
child.on('error', () => { console.error('Unable to start FRAG backend. Check the uv installation.'); process.exitCode = 1; });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
