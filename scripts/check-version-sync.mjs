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
];
const mismatched = exactChecks.filter(([, matches]) => !matches);
if (mismatched.length > 0) {
  console.error(`Version sync failed: package.json is ${packageVersion}, but these exact versions differ:`);
  mismatched.forEach(([label]) => console.error(`- ${label}`));
  process.exit(1);
}

console.log(`Version sync passed: UI, lockfile, backend, health, and README use ${expected}.`);
