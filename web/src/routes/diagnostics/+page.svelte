<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import { ApiError } from '$lib/api/client';
  import { status as statusApi } from '$lib/api/resources';

  import type { StatusResponse } from '$lib/api/types';

  interface LogLine {
    raw: string;
    parsed: Record<string, unknown> | null;
  }

  interface EventEntry {
    type: string;
    payload: Record<string, unknown>;
    at: string;
  }

  let status = $state<StatusResponse | null>(null);
  let statusError = $state<string | null>(null);
  let logs = $state<LogLine[]>([]);
  let events = $state<EventEntry[]>([]);
  let connected = $state(false);
  let socket: WebSocket | null = null;
  let logScroll: HTMLDivElement | null = $state(null);
  let autoscroll = $state(true);

  const MAX_LOG_LINES = 500;
  const MAX_EVENT_ROWS = 50;

  onMount(() => {
    void loadStatus();
    connect();
  });

  onDestroy(() => {
    if (socket) {
      socket.close();
      socket = null;
    }
  });

  async function loadStatus() {
    try {
      status = await statusApi.get();
      statusError = null;
    } catch (err) {
      statusError = err instanceof ApiError ? err.detail : String(err);
    }
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${proto}://${location.host}/ws`);
    socket.onopen = () => {
      connected = true;
    };
    socket.onclose = () => {
      connected = false;
    };
    socket.onerror = () => {
      connected = false;
    };
    socket.onmessage = (msg) => handleFrame(msg.data);
  }

  function handleFrame(data: string) {
    try {
      const env = JSON.parse(data);
      if (env.kind === 'log' && typeof env.record === 'string') {
        appendLog(env.record);
      } else if (env.kind === 'event' && typeof env.type === 'string') {
        events = [
          {
            type: env.type,
            payload: env.payload ?? {},
            at: new Date().toLocaleTimeString(),
          },
          ...events,
        ].slice(0, MAX_EVENT_ROWS);
        // A new device or broker event is worth refetching status.
        void loadStatus();
      }
    } catch {
      // Ignore unparseable frames.
    }
  }

  function appendLog(raw: string) {
    let parsed: Record<string, unknown> | null = null;
    try {
      const v = JSON.parse(raw);
      if (v && typeof v === 'object') parsed = v as Record<string, unknown>;
    } catch {
      parsed = null;
    }
    logs = [...logs, { raw, parsed }].slice(-MAX_LOG_LINES);
    if (autoscroll && logScroll) {
      queueMicrotask(() => {
        if (logScroll) logScroll.scrollTop = logScroll.scrollHeight;
      });
    }
  }

  function levelColor(level?: unknown): string {
    if (level === 'error') return '#b00020';
    if (level === 'warning') return '#b06000';
    if (level === 'info') return '#666';
    if (level === 'debug') return '#999';
    return '#444';
  }

  function clearLogs() {
    logs = [];
  }
</script>

<div class="wrap">
  <h1>Diagnostics</h1>
  <p class="muted">
    Live log stream + event timeline from the running daemon.
    {#if connected}
      <span class="dot ok" title="WebSocket connected"></span> connected
    {:else}
      <span class="dot off" title="WebSocket disconnected"></span> disconnected
    {/if}
  </p>

  {#if statusError}
    <p class="error">Status: {statusError}</p>
  {:else if status}
    <section class="status">
      <h2>Daemon</h2>
      <dl>
        <dt>Version</dt>
        <dd><code>{status.version}</code></dd>
        <dt>MQTT broker</dt>
        <dd>{status.broker_connected ? 'connected' : 'not connected'}</dd>
        <dt>Attached decks</dt>
        <dd>
          {#if status.decks.length === 0}
            <span class="muted">none</span>
          {:else}
            <ul>
              {#each status.decks as d (d.serial)}
                <li><code>{d.serial}</code> ({d.model})</li>
              {/each}
            </ul>
          {/if}
        </dd>
      </dl>
    </section>
  {/if}

  <section class="events">
    <h2>Recent events</h2>
    {#if events.length === 0}
      <p class="muted">No events seen yet on this WebSocket session.</p>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Event</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          {#each events as ev (ev.at + ev.type + JSON.stringify(ev.payload))}
            <tr>
              <td><code>{ev.at}</code></td>
              <td>{ev.type}</td>
              <td><code>{JSON.stringify(ev.payload)}</code></td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <section class="logs">
    <header>
      <h2>Logs</h2>
      <label class="control">
        <input type="checkbox" bind:checked={autoscroll} />
        autoscroll
      </label>
      <button type="button" onclick={clearLogs}>Clear</button>
    </header>
    <div class="log-pane" bind:this={logScroll}>
      {#each logs as line, i (i)}
        {#if line.parsed}
          <div class="line">
            <span class="ts">{(line.parsed.timestamp as string) ?? ''}</span>
            <span class="lvl" style="color: {levelColor(line.parsed.level)}">
              {(line.parsed.level as string) ?? ''}
            </span>
            <span class="logger">{(line.parsed.logger as string) ?? ''}</span>
            <span class="event">{(line.parsed.event as string) ?? ''}</span>
            <span class="rest">
              {Object.entries(line.parsed)
                .filter(([k]) => !['timestamp', 'level', 'logger', 'event'].includes(k))
                .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                .join(' ')}
            </span>
          </div>
        {:else}
          <div class="line">{line.raw}</div>
        {/if}
      {/each}
    </div>
  </section>
</div>

<style>
  .wrap {
    max-width: 64rem;
    margin: 1.5rem auto;
    padding: 0 1.5rem 4rem;
  }
  h1 {
    margin: 0 0 0.25rem;
  }
  .muted {
    color: #666;
  }
  .error {
    color: #b00020;
  }
  .dot {
    display: inline-block;
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    margin-right: 0.25rem;
  }
  .dot.ok {
    background: #2e7d32;
  }
  .dot.off {
    background: #b00020;
  }
  section {
    margin-top: 1.25rem;
    background: #fff;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }
  section h2 {
    margin: 0 0 0.5rem;
    font-size: 1rem;
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 1.25rem;
    margin: 0;
  }
  dt {
    color: #555;
  }
  dd {
    margin: 0;
  }
  ul {
    margin: 0;
    padding-left: 1.25rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }
  th,
  td {
    padding: 0.25rem 0.5rem;
    border-bottom: 1px solid #eee;
    text-align: left;
    vertical-align: top;
  }
  th {
    color: #444;
    font-weight: 500;
    background: #f7f7f7;
  }
  .logs header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  .logs header h2 {
    flex: 1;
    margin: 0;
  }
  .control {
    color: #666;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.875rem;
  }
  .logs button {
    background: transparent;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
  }
  .log-pane {
    background: #0e0e10;
    color: #d0d0d0;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    height: 22rem;
    overflow-y: auto;
    font-family: 'Inter', monospace;
    font-size: 0.8125rem;
    line-height: 1.4;
  }
  .line {
    white-space: pre-wrap;
    word-break: break-word;
    padding: 0.05rem 0;
  }
  .ts {
    color: #888;
    margin-right: 0.5rem;
  }
  .lvl {
    text-transform: uppercase;
    margin-right: 0.5rem;
    font-weight: 600;
  }
  .logger {
    color: #6da3ff;
    margin-right: 0.5rem;
  }
  .event {
    color: #f0e082;
    margin-right: 0.5rem;
  }
  .rest {
    color: #c8c8c8;
  }
  code {
    background: rgba(255, 255, 255, 0.06);
    padding: 0 0.25rem;
    border-radius: 3px;
    font-size: 0.95em;
  }
  section.status code,
  section.events code,
  section.events td code {
    background: #f0f0f0;
    color: #111;
  }
</style>
