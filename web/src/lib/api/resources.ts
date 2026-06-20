/**
 * Typed wrappers around the bare `api` client for each resource.
 *
 * Routes match `src/deckbridge/http/routes_*.py`.
 */

import { api } from './client';

import type {
  CreatePageBody,
  Icon,
  Key,
  KeyBody,
  Page,
  PatchPageBody,
  StatusResponse,
} from './types';

export const status = {
  get: () => api.get<StatusResponse>('/api/status'),
};

export const pages = {
  list: (deck_serial?: string) =>
    api.get<Page[]>('/api/pages', { query: { deck_serial } }),
  get: (id: string) => api.get<Page>(`/api/pages/${encodeURIComponent(id)}`),
  create: (body: CreatePageBody) => api.post<Page>('/api/pages', body),
  patch: (id: string, body: PatchPageBody) =>
    api.patch<Page>(`/api/pages/${encodeURIComponent(id)}`, body),
  remove: (id: string) =>
    api.delete<null>(`/api/pages/${encodeURIComponent(id)}`),
};

export interface TestPressResponse {
  ok: boolean;
  deck_serial: string;
  action_type: string;
}

export const keys = {
  listForPage: (page_id: string) =>
    api.get<Key[]>(`/api/pages/${encodeURIComponent(page_id)}/keys`),
  get: (page_id: string, slot: number) =>
    api.get<Key>(`/api/pages/${encodeURIComponent(page_id)}/keys/${slot}`),
  put: (page_id: string, slot: number, body: KeyBody) =>
    api.put<Key>(`/api/pages/${encodeURIComponent(page_id)}/keys/${slot}`, body),
  remove: (page_id: string, slot: number) =>
    api.delete<null>(`/api/pages/${encodeURIComponent(page_id)}/keys/${slot}`),
  testPress: (page_id: string, slot: number, deck_serial?: string) =>
    api.post<TestPressResponse>(
      `/api/pages/${encodeURIComponent(page_id)}/keys/${slot}/test-press`
        + (deck_serial ? `?deck_serial=${encodeURIComponent(deck_serial)}` : ''),
    ),
};

export const icons = {
  list: () => api.get<Icon[]>('/api/icons'),
  get: (id: string) => api.get<Icon>(`/api/icons/${encodeURIComponent(id)}`),
  rawUrl: (id: string) => `/api/icons/${encodeURIComponent(id)}/raw`,
  remove: (id: string) =>
    api.delete<null>(`/api/icons/${encodeURIComponent(id)}`),
};

/**
 * Whole-config export/import. Snapshot is opaque from the frontend's
 * perspective — we just round-trip whatever the server hands us.
 */
export const config = {
  export: () => api.post<unknown>('/api/config/export'),
  import: (snapshot: unknown) => api.post<unknown>('/api/config/import', snapshot),
};
