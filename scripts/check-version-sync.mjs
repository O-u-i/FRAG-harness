import { readFileSync } from 'node:fs';

const packageManifest = JSON.parse(readFileSync('package.json', 'utf8'));
const packageVersion = packageManifest.version;
const expected = `v${packageVersion}`;
const displayChecks = [
  ['index.html browser title', readFileSync('index.html', 'utf8').includes(`<title>FRAG-harness - ${expected}</title>`)],
  ['FRAG sidebar version', readFileSync('src/App.tsx', 'utf8').includes(`HARNESS / ${expected}`)],
  ['FRAG topbar version', readFileSync('src/App.tsx', 'utf8').includes(`PROTOCOL ${packageVersion}`)],
  ['README heading', readFileSync('README.md', 'utf8').startsWith(`# FRAG-harness ${expected}`)],
];

const missing = displayChecks.filter(([, matches]) => !matches);
if (missing.length > 0) {
  console.error(`Version sync failed: package.json is ${packageVersion}, but ${expected} is missing from:`);
  missing.forEach(([label]) => console.error(`- ${label}`));
  process.exit(1);
}

const packageLock = JSON.parse(readFileSync('package-lock.json', 'utf8'));
const backendPackage = readFileSync('backend/pyproject.toml', 'utf8');
const backendHealth = readFileSync('backend/frag_api/routers/health.py', 'utf8');
const backendApp = readFileSync('backend/frag_api/main.py', 'utf8');
const backendLock = readFileSync('backend/uv.lock', 'utf8');
const governance = readFileSync('backend/frag_api/schemas/governance.py', 'utf8');
const exactChecks = [
  ['package name', packageManifest.name === 'frag-harness'],
  ['package-lock name', packageLock.name === 'frag-harness' && packageLock.packages[''].name === 'frag-harness'],
  ['package-lock root version', packageLock.version === packageVersion && packageLock.packages[''].version === packageVersion],
  ['backend package version', backendPackage.includes(`version = "${packageVersion}"`)],
  ['backend lock version', new RegExp(`name = "frag-harness-backend"\\r?\\nversion = "${packageVersion.replaceAll('.', '\\.') }"`).test(backendLock)],
  ['backend OpenAPI version', backendApp.includes(`version="${packageVersion}"`)],
  ['backend package name', backendPackage.includes('name = "frag-harness-backend"')],
  ['backend health version', backendHealth.includes(`"serviceVersion": "${packageVersion}"`)],
  ['backend health identity', backendHealth.includes('"service": "frag-harness"')],
  ['review HTML title', readFileSync('agents.html', 'utf8').includes(`FRAG Review · ${packageVersion}`)],
  ['review title and footer', readFileSync('src/agents/AgentReviewApp.tsx', 'utf8').includes(`FRAG Review · ${packageVersion}`)],
  ['VSIX version', JSON.parse(readFileSync('integrations/vscode/bridge/package.json', 'utf8')).version === packageVersion],
  ['installed launcher version', readFileSync('integrations/vscode/bridge/host-launcher.cjs', 'utf8').includes(`serviceVersion === '${packageVersion}'`)],
  ['extension default installation', readFileSync('integrations/vscode/bridge/extension.cjs', 'utf8').includes(`'host', '${packageVersion}'`)],
  ['installer default version', readFileSync('integrations/vscode/install-host.ps1', 'utf8').includes(`FRAG\\host\\${packageVersion}`)],
  ['VS Code README version', readFileSync('integrations/vscode/README.md', 'utf8').includes(`/ ${expected}`)],
  ['bridge README version', readFileSync('integrations/vscode/bridge/README.md', 'utf8').startsWith(`# FRAG Local Host ${expected}`)],
  ['review README version', readFileSync('src/agents/README.md', 'utf8').startsWith(`# FRAG Review ${expected}`)],
  ['prepared request host version', governance.includes(`HOST_VERSION = "${packageVersion}"`)],
];
const mismatched = exactChecks.filter(([, matches]) => !matches);
if (mismatched.length > 0) {
  console.error(`Version sync failed: package.json is ${packageVersion}, but these exact versions differ:`);
  mismatched.forEach(([label]) => console.error(`- ${label}`));
  process.exit(1);
}

console.log(`Version sync passed: UI, lockfile, backend, health, and README use ${expected}.`);
