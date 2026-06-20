import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';

import { auth } from '$lib/stores/auth.svelte';

import type { LayoutLoad } from './$types';

// Pure SPA: no SSR, no prerendering.
export const ssr = false;
export const prerender = false;

const PUBLIC_ROUTES = new Set(['/setup', '/login']);

export const load: LayoutLoad = async ({ url }) => {
  if (!browser) return {};

  await auth.refresh();
  const path = url.pathname;

  if (auth.state === 'setup-needed' && path !== '/setup') {
    throw redirect(307, '/setup');
  }
  if (auth.state === 'unauthenticated' && !PUBLIC_ROUTES.has(path)) {
    throw redirect(307, '/login');
  }
  if (auth.state === 'authenticated' && PUBLIC_ROUTES.has(path)) {
    throw redirect(307, '/editor');
  }

  return {};
};
