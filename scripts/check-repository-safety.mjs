import { execFileSync } from 'node:child_process';
import { existsSync, lstatSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptsDir, '..');
const tracked = execFileSync('git', [
  'ls-files', '--cached', '--others', '--exclude-standard', '-z',
], { encoding: 'utf8' }).split('\0').filter(Boolean);

const violations = [];
const privateParts = new Set(['.agents', '.codex', '.obsidian', '.tmp', 'private', 'personal', 'real-data', 'imports', 'exports', 'attachments']);
for (const entry of execFileSync('git', ['ls-files', '--stage', '-z'], { encoding: 'utf8' }).split(String.fromCharCode(0)).filter(Boolean)) {
  const [record, name] = entry.split(String.fromCharCode(9));
  if (!['100644', '100755'].includes(record.split(' ')[0])) violations.push(`${name}: linked file or submodule must not be tracked`);
}
const forbiddenArtifact = /(^|\/)(\.env(?:\..+)?$|.+\.(?:sqlite3?|db|csv|tsv|xlsx?|pdf|docx?|png|jpe?g|webp)$)/i;
const reviewedImage = 'docs/images/management.png';
for (const path of tracked) {
  const parts = path.toLowerCase().split('/');
  if (parts.some(part => privateParts.has(part) || part.startsWith('.local-') || ['agents.md', 'agents.override.md', 'fc.env'].includes(part))
      || (path.startsWith('local-sources/') && path !== 'local-sources/README.md')) {
    violations.push(`${path}: private state, source, or agent instructions must not enter Git`);
  }
  if (path === 'AGENTS.md' || path.startsWith('.agents/') || path.startsWith('docs/codex-skills/')
      || path === 'scripts/check-skill-lock.mjs' || path === 'docs/history-transition.md') {
    violations.push(`${path}: local agent or migration file must not be tracked`);
  }
  if (forbiddenArtifact.test(path) && !path.endsWith('.env.example') && path !== reviewedImage) {
    violations.push(`${path}: tracked private-data or secret artifact type`);
  }
  if (!existsSync(path)) continue;
  if (!lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) {
    violations.push(`${path}: nonregular or linked repository input`);
    continue;
  }
  // Only this visually reviewed synthetic screenshot is an allowed binary input.
  if (path === reviewedImage) continue;
  const source = readFileSync(path, 'utf8');
  const assignments = [...source.matchAll(/FINANCE_CORE_ACCESS_TOKEN\s*=\s*['"]?([^\s#'"]+)/g)];
  for (const match of assignments) {
    const value = match[1];
    if (!value.startsWith('<') && !value.startsWith('synthetic-')) {
      violations.push(`${path}: non-placeholder FC access token assignment`);
    }
  }
  const bearerValues = [...source.matchAll(/Bearer\s+([A-Za-z0-9._${}<>-]{12,})/g)].map((match) => match[1]);
  if (bearerValues.some((value) => !value.startsWith('<') && !value.startsWith('${') && !value.startsWith('{') && !value.startsWith('synthetic-'))) {
    violations.push(`${path}: non-placeholder Bearer credential`);
  }
}

const readme = readFileSync(path.join(repoRoot, 'README.md'), 'utf8');
if (/\b[A-Z]:\\|C:\/Users\/|\bSoren\b|\bXin\b|\bSFOS\b/i.test(readme)) {
  violations.push('README.md: personal identity, absolute machine path, or obsolete project label');
}

if (violations.length) {
  console.error('Repository-safety check failed:');
  violations.forEach((item) => console.error(`- ${item}`));
  process.exit(1);
}
console.log('Repository-safety check passed: no tracked secret/private-data artifact or literal credential found.');
