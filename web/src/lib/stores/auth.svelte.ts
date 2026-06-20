/**
 * Auth state machine + actions.
 *
 * The state lifecycle:
 *
 *     unknown ──refresh──► setup-needed ──completeSetup──► authenticated
 *         │                       │                             ▲
 *         │                       └──(any visit)───────────────┐│
 *         │                                                    ││
 *         └──refresh──► unauthenticated ──login──► authenticated
 *                              ▲                          │
 *                              └──────── logout ──────────┘
 *
 * `refresh()` calls /api/setup/needed first, then /api/me — the layout's
 * load function calls it on every navigation so the state is always fresh.
 */

import { ApiError, api } from '$lib/api/client';

export type AuthState = 'unknown' | 'setup-needed' | 'unauthenticated' | 'authenticated';

class AuthStore {
  state = $state<AuthState>('unknown');
  lastError = $state<string | null>(null);

  async refresh(): Promise<AuthState> {
    try {
      const setup = await api.get<{ needed: boolean }>('/api/setup/needed');
      if (setup.needed) {
        this.state = 'setup-needed';
        return this.state;
      }
    } catch (err) {
      // Backend unreachable — treat as unknown so the UI can show an error,
      // not a redirect loop.
      this.state = 'unknown';
      this.lastError = err instanceof Error ? err.message : String(err);
      return this.state;
    }

    try {
      await api.get('/api/me');
      this.state = 'authenticated';
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        this.state = 'unauthenticated';
      } else {
        this.state = 'unknown';
        this.lastError = err instanceof Error ? err.message : String(err);
      }
    }
    return this.state;
  }

  async login(password: string): Promise<void> {
    try {
      await api.post('/api/login', { password });
      this.state = 'authenticated';
      this.lastError = null;
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          this.state = 'setup-needed';
          throw new Error('Setup required before login.');
        }
        if (err.status === 401) {
          throw new Error('Invalid password.');
        }
      }
      throw err;
    }
  }

  async logout(): Promise<void> {
    try {
      await api.post('/api/logout');
    } catch {
      // Ignore — even if the server rejected, we treat the local session as cleared.
    }
    this.state = 'unauthenticated';
    this.lastError = null;
  }

  async completeSetup(password: string): Promise<void> {
    await api.post('/api/setup/complete', { password });
    // Backend auto-logs us in after setup completion.
    this.state = 'authenticated';
    this.lastError = null;
  }
}

export const auth = new AuthStore();
