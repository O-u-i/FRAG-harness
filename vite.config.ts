import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  build: mode === 'agents' ? { rollupOptions: { input: resolve('agents.html') } } : {},
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        configure(proxy) {
          proxy.on('error', (_error, _request, response) => {
            if ('writeHead' in response && !response.headersSent) {
              response.writeHead(503, { 'Content-Type': 'application/json' });
              response.end(JSON.stringify({ error: {
                code: 'FRAG_BACKEND_UNAVAILABLE',
                issues: [],
                message: 'FRAG backend is unavailable. Run npm run dev to start both services on localhost.',
              } }));
            }
          });
        },
      },
      '/plugins': 'http://127.0.0.1:8787',
    },
  },
}));
