<script lang="ts">
  import { onMount } from 'svelte';

  import { api, ApiError } from '$lib/api/client';
  import { config as configApi } from '$lib/api/resources';

  interface Prefs {
    mqtt_host: string | null;
    mqtt_port: number;
    mqtt_username: string | null;
    mqtt_tls: boolean;
    ha_discovery_enabled: boolean;
    has_api_token: boolean;
  }

  // Broker form
  let prefs = $state<Prefs | null>(null);
  let mqtt_host = $state('');
  let mqtt_port = $state(1883);
  let mqtt_username = $state('');
  let mqtt_password = $state('');
  let mqtt_tls = $state(false);
  let ha_discovery_enabled = $state(true);
  let savingBroker = $state(false);
  let brokerMsg = $state<string | null>(null);

  // Password change form
  let currentPassword = $state('');
  let newPassword = $state('');
  let savingPassword = $state(false);
  let passwordMsg = $state<string | null>(null);

  // API token rotation
  let rotatingToken = $state(false);
  let lastToken = $state<string | null>(null);
  let tokenMsg = $state<string | null>(null);

  // Config export / import
  let exporting = $state(false);
  let importing = $state(false);
  let configMsg = $state<string | null>(null);
  let importFileInput: HTMLInputElement | null = $state(null);

  onMount(loadPrefs);

  async function loadPrefs() {
    try {
      prefs = await api.get<Prefs>('/api/settings');
      mqtt_host = prefs.mqtt_host ?? '';
      mqtt_port = prefs.mqtt_port;
      mqtt_username = prefs.mqtt_username ?? '';
      mqtt_tls = prefs.mqtt_tls;
      ha_discovery_enabled = prefs.ha_discovery_enabled;
    } catch (err) {
      brokerMsg = err instanceof ApiError ? err.detail : String(err);
    }
  }

  async function saveBroker(e: Event) {
    e.preventDefault();
    savingBroker = true;
    brokerMsg = null;
    try {
      const body: Record<string, unknown> = {
        mqtt_host: mqtt_host || null,
        mqtt_port,
        mqtt_username: mqtt_username || null,
        mqtt_tls,
        ha_discovery_enabled,
      };
      if (mqtt_password) body.mqtt_password = mqtt_password;
      prefs = await api.patch<Prefs>('/api/settings', body);
      mqtt_password = '';
      brokerMsg = 'Saved.';
    } catch (err) {
      brokerMsg = err instanceof ApiError ? err.detail : String(err);
    } finally {
      savingBroker = false;
    }
  }

  async function changePassword(e: Event) {
    e.preventDefault();
    if (newPassword.length < 8) {
      passwordMsg = 'New password must be at least 8 characters.';
      return;
    }
    savingPassword = true;
    passwordMsg = null;
    try {
      await api.post('/api/settings/password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      currentPassword = '';
      newPassword = '';
      passwordMsg = 'Password changed.';
    } catch (err) {
      passwordMsg = err instanceof ApiError ? err.detail : String(err);
    } finally {
      savingPassword = false;
    }
  }

  async function exportConfig() {
    exporting = true;
    configMsg = null;
    try {
      const snapshot = await configApi.export();
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      a.href = url;
      a.download = `deckbridge-config-${ts}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      configMsg = 'Exported. Treat the downloaded file as a secret — it contains your password hash and API token hash.';
    } catch (err) {
      configMsg = err instanceof ApiError ? err.detail : String(err);
    } finally {
      exporting = false;
    }
  }

  async function importConfig(e: Event) {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    if (
      !confirm(
        'Importing replaces ALL current configuration (decks, pages, keys, settings). Continue?',
      )
    ) {
      target.value = '';
      return;
    }
    importing = true;
    configMsg = null;
    try {
      const text = await file.text();
      const snapshot = JSON.parse(text);
      await configApi.import(snapshot);
      configMsg = 'Imported. Reloading…';
      setTimeout(() => location.reload(), 800);
    } catch (err) {
      if (err instanceof SyntaxError) {
        configMsg = `Could not parse JSON: ${err.message}`;
      } else {
        configMsg = err instanceof ApiError ? err.detail : String(err);
      }
    } finally {
      importing = false;
      target.value = '';
    }
  }

  async function rotateToken() {
    rotatingToken = true;
    tokenMsg = null;
    try {
      const res = await api.post<{ token: string }>('/api/settings/token');
      lastToken = res.token;
      tokenMsg = 'New token generated. Copy it now — it will not be shown again.';
      if (prefs) prefs.has_api_token = true;
    } catch (err) {
      tokenMsg = err instanceof ApiError ? err.detail : String(err);
    } finally {
      rotatingToken = false;
    }
  }
</script>

<div class="wrap">
  <h1>Settings</h1>

  <section>
    <h2>MQTT broker</h2>
    <p class="muted">
      DeckBridge connects to your existing MQTT broker. If you don't have one,
      enable the bundled Mosquitto in your install.
    </p>
    <form onsubmit={saveBroker}>
      <label>
        <span>Host</span>
        <input bind:value={mqtt_host} placeholder="broker.lan" disabled={savingBroker} />
      </label>
      <label>
        <span>Port</span>
        <input
          type="number"
          bind:value={mqtt_port}
          min="1"
          max="65535"
          disabled={savingBroker}
        />
      </label>
      <label>
        <span>Username (optional)</span>
        <input bind:value={mqtt_username} disabled={savingBroker} />
      </label>
      <label>
        <span>Password (leave blank to keep current)</span>
        <input
          type="password"
          autocomplete="new-password"
          bind:value={mqtt_password}
          disabled={savingBroker}
        />
      </label>
      <label class="checkbox">
        <input type="checkbox" bind:checked={mqtt_tls} disabled={savingBroker} />
        <span>Use TLS</span>
      </label>
      <label class="checkbox">
        <input
          type="checkbox"
          bind:checked={ha_discovery_enabled}
          disabled={savingBroker}
        />
        <span>Publish Home Assistant Discovery payloads</span>
      </label>
      <div class="row">
        <button type="submit" disabled={savingBroker}>
          {savingBroker ? 'Saving…' : 'Save'}
        </button>
        {#if brokerMsg}<span class="msg">{brokerMsg}</span>{/if}
      </div>
    </form>
  </section>

  <section>
    <h2>Admin password</h2>
    <form onsubmit={changePassword}>
      <label>
        <span>Current password</span>
        <input
          type="password"
          autocomplete="current-password"
          bind:value={currentPassword}
          required
          disabled={savingPassword}
        />
      </label>
      <label>
        <span>New password (min 8 characters)</span>
        <input
          type="password"
          autocomplete="new-password"
          bind:value={newPassword}
          required
          minlength="8"
          disabled={savingPassword}
        />
      </label>
      <div class="row">
        <button type="submit" disabled={savingPassword}>
          {savingPassword ? 'Saving…' : 'Change password'}
        </button>
        {#if passwordMsg}<span class="msg">{passwordMsg}</span>{/if}
      </div>
    </form>
  </section>

  <section>
    <h2>Inbound webhook token</h2>
    <p class="muted">
      Bearer token used by external apps to update key state via
      <code>POST /api/keys/{'{id}'}/state</code> (consumer ships in M7).
      Rotation always invalidates the previous token.
    </p>
    <p>
      Status:
      {prefs?.has_api_token ? 'a token is currently active' : 'no token configured'}.
    </p>
    <button type="button" onclick={rotateToken} disabled={rotatingToken}>
      {rotatingToken ? 'Generating…' : prefs?.has_api_token ? 'Rotate token' : 'Generate token'}
    </button>
    {#if tokenMsg}<p class="msg">{tokenMsg}</p>{/if}
    {#if lastToken}
      <pre class="token">{lastToken}</pre>
    {/if}
  </section>

  <section>
    <h2>Backup &amp; restore</h2>
    <p class="muted">
      Export the entire configuration (decks, pages, keys, icon metadata,
      preferences) as a single JSON file. Import replaces everything; the
      uploaded icon PNG bytes are NOT included in the export, so after a
      restore on a fresh install you may need to re-upload custom icons.
    </p>
    <div class="row">
      <button type="button" onclick={exportConfig} disabled={exporting}>
        {exporting ? 'Exporting…' : 'Export config'}
      </button>
      <button
        type="button"
        onclick={() => importFileInput?.click()}
        disabled={importing}
      >
        {importing ? 'Importing…' : 'Import config…'}
      </button>
      <input
        bind:this={importFileInput}
        type="file"
        accept="application/json,.json"
        onchange={importConfig}
        style="display: none"
      />
    </div>
    {#if configMsg}<p class="msg">{configMsg}</p>{/if}
  </section>
</div>

<style>
  .wrap {
    max-width: 48rem;
    margin: 2rem auto;
    padding: 0 1.5rem 4rem;
  }
  section {
    background: #fff;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }
  h2 {
    margin-bottom: 0.25rem;
  }
  .muted {
    color: #666;
    margin: 0 0 1rem;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
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
  label.checkbox {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
  input[type='password'],
  input[type='number'],
  input:not([type]) {
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
  .row {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 0.5rem;
  }
  button {
    background: #1d1d1d;
    color: #fff;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
  }
  button:disabled {
    background: #888;
    cursor: not-allowed;
  }
  .msg {
    color: #444;
    font-size: 0.875rem;
  }
  .token {
    background: #1d1d1d;
    color: #f5f5f5;
    padding: 0.75rem;
    border-radius: 6px;
    font-family: 'Inter', monospace;
    font-size: 0.875rem;
    white-space: pre-wrap;
    word-break: break-all;
    margin-top: 0.5rem;
  }
  code {
    background: #f0f0f0;
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
  }
</style>
