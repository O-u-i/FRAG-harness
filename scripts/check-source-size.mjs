import { readdirSync, readFileSync } from 'node:fs';
import { extname, join, relative } from 'node:path';

const ROOTS = ['src', 'shared', 'backend/frag_api', 'backend/tests', 'backend/pi-worker', 'scripts'];
const ROOT_FILES = ['vite.config.ts'];
const EXTENSIONS = new Set(['.ts', '.tsx', '.py', '.css', '.mjs']);
const IGNORED_PARTS = new Set(['node_modules', '.venv', '__pycache__', 'dist', '.tmp', 'vendor']);
const WARNING_LINES = 350;
const MAX_LINES = 500;

function collectFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return IGNORED_PARTS.has(entry.name) ? [] : collectFiles(path);
    }
    return EXTENSIONS.has(extname(entry.name)) ? [path] : [];
  });
}

const findings = [...ROOTS.flatMap(collectFiles), ...ROOT_FILES]
  .map((path) => ({
    path: relative(process.cwd(), path).replaceAll('\\', '/'),
    lines: readFileSync(path, 'utf8').split(/\r?\n/).length,
  }))
  .filter(({ lines }) => lines >= WARNING_LINES)
  .sort((left, right) => right.lines - left.lines);

for (const finding of findings) {
  const level = finding.lines > MAX_LINES ? 'ERROR' : 'WARN';
  console.log(`${level} ${finding.lines.toString().padStart(4)} ${finding.path}`);
}

const oversized = findings.filter(({ lines }) => lines > MAX_LINES);
if (oversized.length > 0) {
  console.error(`Source-size check failed: ${oversized.length} file(s) exceed ${MAX_LINES} lines.`);
  process.exit(1);
}

console.log(`Source-size check passed: no project-owned source file exceeds ${MAX_LINES} lines.`);
