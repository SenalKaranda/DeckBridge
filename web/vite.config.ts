import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// During `npm run dev`, the Vite dev server proxies /api and /ws to the
// FastAPI backend running on port 7878. In production both backend and
// frontend are served by FastAPI from the same origin, so no proxy is needed.
export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://localhost:7878',
        changeOrigin: false,
      },
      '/ws': {
        target: 'ws://localhost:7878',
        ws: true,
        changeOrigin: false,
      },
    },
  },
});
