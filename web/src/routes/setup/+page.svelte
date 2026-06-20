<script lang="ts">
  import { goto } from '$app/navigation';

  import { auth } from '$lib/stores/auth.svelte';

  let password = $state('');
  let confirm = $state('');
  let loading = $state(false);
  let error = $state<string | null>(null);

  let mismatch = $derived(password !== confirm);
  let tooShort = $derived(password.length > 0 && password.length < 8);
  let canSubmit = $derived(
    password.length >= 8 && !mismatch && !loading,
  );

  async function submit(e: Event) {
    e.preventDefault();
    if (!canSubmit) return;
    loading = true;
    error = null;
    try {
      await auth.completeSetup(password);
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
    <h1>Welcome to DeckBridge</h1>
    <p class="muted">
      Set the admin password for the web interface. You can change it later in
      Settings.
    </p>

    <form onsubmit={submit}>
      <label>
        <span>New password</span>
        <input
          type="password"
          autocomplete="new-password"
          bind:value={password}
          required
          minlength="8"
          disabled={loading}
        />
      </label>
      <label>
        <span>Confirm</span>
        <input
          type="password"
          autocomplete="new-password"
          bind:value={confirm}
          required
          disabled={loading}
        />
      </label>

      {#if tooShort}
        <p class="hint">Use at least 8 characters.</p>
      {:else if mismatch && confirm.length > 0}
        <p class="hint">Passwords do not match.</p>
      {/if}

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" disabled={!canSubmit}>
        {loading ? 'Setting up…' : 'Continue'}
      </button>
    </form>

    <p class="footnote">
      DeckBridge is designed for trusted local networks only. The admin
      password protects the web interface; it is not a substitute for keeping
      the daemon off the public internet.
    </p>
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
    max-width: 420px;
    width: 100%;
  }
  h1 {
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
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
  .hint {
    color: #b06000;
    font-size: 0.875rem;
    margin: 0;
  }
  .error {
    color: #b00020;
    font-size: 0.875rem;
    margin: 0;
  }
  .footnote {
    color: #888;
    font-size: 0.8125rem;
    margin-top: 1.5rem;
  }
</style>
