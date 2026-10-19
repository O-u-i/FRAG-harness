import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  plugins:[react()], base:'./', publicDir:false,
  server: {
    host: '127.0.0.1',
    fs: {
      strict: true,
      allow: ['src', 'node_modules', 'index.html'].map(path => fileURLToPath(new URL(path, import.meta.url))),
      deny: ['.env', '.env.*', '*.{crt,pem,key}', '**/.git/**',
        '**/{backend,local-sources,private,personal,imports,exports,real-data,.tmp,.agents,.codex,.local-runtime,.local-index,.local-plugins,.local-guidance,.local-acceptance}/**',
        '**/AGENTS*.md', '*.{sqlite,sqlite3,db,csv,tsv,xls,xlsx}'],
    },
  },
  build:{outDir:'.tmp/agents-dist',emptyOutDir:false},
});
