import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In development the dev server proxies /api to the backend, so the frontend
// code never needs an absolute URL. In Docker nginx does the same job.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
