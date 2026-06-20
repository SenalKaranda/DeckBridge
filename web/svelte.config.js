import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // Build a single-page-app bundle into src/deckbridge/web_dist/ so the
    // FastAPI backend can mount it as a static directory at runtime.
    adapter: adapter({
      pages: '../src/deckbridge/web_dist',
      assets: '../src/deckbridge/web_dist',
      fallback: 'index.html',
      strict: false,
    }),
  },
};

export default config;
