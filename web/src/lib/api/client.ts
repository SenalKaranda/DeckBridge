/**
 * Thin fetch wrapper for the DeckBridge HTTP API.
 *
 * - Sends the session cookie (same-origin) so the SessionMiddleware on the
 *   backend can authenticate the request.
 * - Throws ApiError on non-2xx responses with the parsed detail (FastAPI's
 *   {"detail": "..."} shape).
 * - Returns parsed JSON for 2xx; returns null for 204 No Content.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly url: string,
  ) {
    super(`HTTP ${status} on ${url}: ${detail}`);
    this.name = 'ApiError';
  }
}

type Body = unknown;

interface ApiOptions {
  query?: Record<string, string | undefined>;
}

async function request<T>(
  method: string,
  path: string,
  body?: Body,
  opts: ApiOptions = {},
): Promise<T> {
  const url = buildUrl(path, opts.query);
  const init: RequestInit = {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
  const res = await fetch(url, init);
  if (res.status === 204) {
    return null as T;
  }
  if (!res.ok) {
    const detail = await extractDetail(res);
    throw new ApiError(res.status, detail, url);
  }
  return (await res.json()) as T;
}

function buildUrl(path: string, query?: Record<string, string | undefined>): string {
  if (!query) return path;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== '') usp.set(k, v);
  }
  const qs = usp.toString();
  return qs ? `${path}?${qs}` : path;
}

async function extractDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string | unknown };
    if (typeof data.detail === 'string') return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `status ${res.status}`;
  }
}

// ---- multipart helper for icon uploads ----------------------------------

export async function uploadIcon(file: File, name = ''): Promise<unknown> {
  const fd = new FormData();
  fd.append('file', file);
  if (name) fd.append('name', name);
  const res = await fetch('/api/icons', {
    method: 'POST',
    credentials: 'same-origin',
    body: fd,
  });
  if (!res.ok) throw new ApiError(res.status, await extractDetail(res), '/api/icons');
  return await res.json();
}

// ---- public surface ------------------------------------------------------

export const api = {
  get: <T = unknown>(path: string, opts?: ApiOptions) => request<T>('GET', path, undefined, opts),
  post: <T = unknown>(path: string, body?: Body) => request<T>('POST', path, body),
  put: <T = unknown>(path: string, body?: Body) => request<T>('PUT', path, body),
  patch: <T = unknown>(path: string, body?: Body) => request<T>('PATCH', path, body),
  delete: <T = unknown>(path: string) => request<T>('DELETE', path),
};
