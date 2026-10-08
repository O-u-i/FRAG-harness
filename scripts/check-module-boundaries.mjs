import { readdirSync, readFileSync } from 'node:fs';
import { extname, join, relative } from 'node:path';

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.jsx', '.py']);
const IGNORED_PARTS = new Set(['node_modules', '.venv', '__pycache__', 'dist', '.tmp']);

function collectFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return IGNORED_PARTS.has(entry.name) ? [] : collectFiles(path);
    }
    return SOURCE_EXTENSIONS.has(extname(entry.name)) ? [path] : [];
  });
}

const violations = [];
const frontendFiles = [...collectFiles('src'), ...collectFiles('shared')];

for (const path of frontendFiles) {
  const normalized = relative(process.cwd(), path).replaceAll('\\', '/');
  const source = readFileSync(path, 'utf8');
  const imports = [...source.matchAll(/(?:import|export)\s+(?:[^'\"]+\s+from\s+)?['\"]([^'\"]+)['\"]/g)]
    .map((match) => match[1]);

  if (normalized.startsWith('src/domain/')) {
    for (const imported of imports) {
      if (
        imported === 'react' ||
        imported.includes('/pages/') ||
        imported.includes('/hooks/') ||
        imported.includes('/api/') ||
        imported.includes('/components/')
      ) {
        violations.push(`${normalized}: domain must not import ${imported}`);
      }
    }
  }

  if (normalized.startsWith('src/api/') && !normalized.endsWith('.test.ts') && !normalized.endsWith('.test.tsx')) {
    for (const imported of imports) {
      if (imported.includes('/pages/') || imported.includes('/hooks/') || imported.includes('/components/')) {
        violations.push(`${normalized}: api client must not import ${imported}`);
      }
    }
  }

  if (normalized.startsWith('src/pages/')) {
    for (const imported of imports) {
      if (imported.includes('/api/') || imported.includes('/hooks/') || imported.includes('/features/')) {
        violations.push(`${normalized}: page composition must not import ${imported}`);
      }
    }
  }

  if (source.includes('OPENAI_API_KEY') || source.includes('VITE_OPENAI')) {
    violations.push(`${normalized}: OpenAI credentials must remain in the backend provider layer`);
  }
}

for (const path of collectFiles('backend/frag_api')) {
  const normalized = relative(process.cwd(), path).replaceAll('\\', '/');
  const source = readFileSync(path, 'utf8');
  if (/(?:^|\n)\s*(?:from|import)\s+(?:sfos_api|finance_core|frag_api\.clients\.)/m.test(source)) {
    violations.push(`${normalized}: core cannot import former finance runtime modules`);
  }
  const pythonImports = [...source.matchAll(/^(?:from|import)\s+(frag_api\.[A-Za-z0-9_.]+)/gm)]
    .map((match) => match[1]);
  if (/^(?:from|import) openai\b/m.test(source) && !normalized.startsWith('backend/frag_api/providers/')) {
    violations.push(`${normalized}: OpenAI SDK imports are restricted to backend/frag_api/providers`);
  }

  const forbidden = normalized.startsWith('backend/frag_api/schemas/')
    ? ['routers', 'services', 'providers', 'repositories', 'db']
    : normalized.startsWith('backend/frag_api/providers/')
      ? ['routers', 'services', 'repositories', 'db']
      : normalized.startsWith('backend/frag_api/repositories/')
        ? ['routers', 'services', 'providers']
        : normalized.startsWith('backend/frag_api/services/')
          ? ['routers']
          : normalized.startsWith('backend/frag_api/routers/')
            ? ['repositories', 'providers']
            : [];
  for (const imported of pythonImports) {
    if (forbidden.some((layer) => imported.startsWith(`frag_api.${layer}`))) {
      violations.push(`${normalized}: layer must not import ${imported}`);
    }
  }
}

if (violations.length > 0) {
  console.error('Module-boundary check failed:');
  violations.forEach((violation) => console.error(`- ${violation}`));
  process.exit(1);
}

console.log('Module-boundary check passed.');
