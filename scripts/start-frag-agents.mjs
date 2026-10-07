import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
if (!existsSync(resolve(root, 'dist/index.html'))) throw new Error('Run npm run build before starting FRAG Agents.');
const address = 'ws://127.0.0.1:8787/api/agents/ahp';
const settings = {
  'chat.remoteAgentHostsEnabled': true,
  'chat.remoteAgentHostsAutoConnect': true,
  'chat.remoteAgentHosts': [{ name: 'FRAG', address }],
};
const local = resolve(root, '.local-runtime/vscode');
mkdirSync(local, { recursive: true });
writeFileSync(resolve(local, 'connection.settings.json'), JSON.stringify(settings, null, 2) + '\n');
console.log('FRAG native Agent Host: ' + address);
console.log('Review: http://127.0.0.1:8787/review');
console.log('Merge .local-runtime/vscode/connection.settings.json into your Agents settings. Existing settings are not edited.');
const child = spawn('uv', ['run', '--offline', '--project', 'backend', '--cache-dir', '.tmp/uv-cache',
  'uvicorn', 'frag_api.main:app', '--host', '127.0.0.1', '--port', '8787', '--no-access-log'], {
  cwd: root, stdio: 'inherit', windowsHide: true, env: { ...process.env, FRAG_AGENT_HOST_ENABLED: '1' },
});
child.on('error', () => { console.error('Unable to start the FRAG host. Check uv and the backend environment.'); process.exitCode = 1; });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
