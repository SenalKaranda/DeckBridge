<script lang="ts">
  import { goto } from '$app/navigation';

  import { auth } from '$lib/stores/auth.svelte';

  let password = $state('');
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function submit(e: Event) {
    e.preventDefault();
    if (loading || !password) return;
    loading = true;
    error = null;
    try {
      await auth.login(password);
      await goto('/editor', { replaceState: true });
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }
</script>

<div class="wrap">
  <div class="card">
    <h1>DeckBridge</h1>
    <p class="muted">Sign in to continue.</p>

    <form onsubmit={submit}>
      <label>
        <span>Password</span>
        <input
          type="password"
          autocomplete="current-password"
          bind:value={password}
          required
          disabled={loading}
        />
      </label>

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" disabled={loading || !password}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  </div>
</div>

<style>
  .wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 1rem;
  }
  .card {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    padding: 2rem;
    max-width: 360px;
    width: 100%;
  }
  h1 {
    font-size: 1.5rem;
    margin-bottom: 0.25rem;
  }
  .muted {
    color: #666;
    margin-top: 0;
    margin-bottom: 1.5rem;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  label span {
    font-size: 0.875rem;
    color: #444;
  }
  input {
    padding: 0.5rem 0.625rem;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    font: inherit;
  }
  input:focus {
    outline: 2px solid #4c8bf5;
    outline-offset: -1px;
    border-color: #4c8bf5;
  }
  button {
    margin-top: 0.5rem;
    background: #1d1d1d;
    color: #fff;
    border: none;
    padding: 0.625rem 1rem;
    border-radius: 6px;
  }
  button:disabled {
    background: #888;
    cursor: not-allowed;
  }
  .error {
    color: #b00020;
    font-size: 0.875rem;
    margin: 0;
  }
</style>
