<script lang="ts">
  import { ApiError, uploadIcon } from '$lib/api/client';
  import { icons as iconsApi } from '$lib/api/resources';

  import type { Icon } from '$lib/api/types';

  interface Props {
    open: boolean;
    selectedIconId: string | null;
    onSelect: (iconId: string | null) => void;
    onClose: () => void;
  }

  let { open, selectedIconId, onSelect, onClose }: Props = $props();

  let allIcons = $state<Icon[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let search = $state('');
  let uploadInput: HTMLInputElement | null = $state(null);

  $effect(() => {
    if (open) void loadIcons();
  });

  async function loadIcons() {
    loading = true;
    error = null;
    try {
      allIcons = await iconsApi.list();
    } catch (err) {
      error = err instanceof ApiError ? err.detail : String(err);
    } finally {
      loading = false;
    }
  }

  let filtered = $derived(
    search
      ? allIcons.filter(
          (i) =>
            i.name.toLowerCase().includes(search.toLowerCase()) ||
            i.id.toLowerCase().includes(search.toLowerCase()),
        )
      : allIcons,
  );

  async function handleUpload(event: Event) {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    try {
      const uploaded = (await uploadIcon(file, file.name)) as Icon;
      await loadIcons();
      onSelect(uploaded.id);
    } catch (err) {
      error = err instanceof ApiError ? err.detail : String(err);
    } finally {
      if (uploadInput) uploadInput.value = '';
    }
  }
</script>

<svelte:window onkeydown={(e) => open && e.key === 'Escape' && onClose()} />

{#if open}
  <div class="backdrop" role="presentation" onclick={onClose}></div>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Icon picker">
    <header>
      <h2>Choose an icon</h2>
      <button type="button" class="close" onclick={onClose} aria-label="Close">×</button>
    </header>

    <div class="toolbar">
      <input
        type="search"
        class="control"
        placeholder="Search icons…"
        bind:value={search}
        autocomplete="off"
      />
      <label class="btn btn--ghost btn--sm upload">
        Upload…
        <input
          bind:this={uploadInput}
          type="file"
          accept="image/png,image/jpeg"
          hidden
          onchange={handleUpload}
        />
      </label>
      <button type="button" class="btn btn--subtle btn--sm" onclick={() => onSelect(null)}>
        No icon
      </button>
    </div>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    {#if loading && allIcons.length === 0}
      <p class="state">Loading…</p>
    {:else if filtered.length === 0}
      <p class="state">No matching icons.</p>
    {:else}
      <div class="grid">
        {#each filtered as icon (icon.id)}
          <button
            type="button"
            class="cell"
            class:selected={icon.id === selectedIconId}
            onclick={() => onSelect(icon.id)}
            title={`${icon.name} (${icon.source})`}
          >
            <img src={iconsApi.rawUrl(icon.id)} alt={icon.name} loading="lazy" />
            <span class="cap">{icon.name}</span>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(12, 13, 17, 0.5);
    backdrop-filter: blur(2px);
    z-index: 100;
  }
  .modal {
    position: fixed;
    inset: 6vh 50% auto;
    transform: translateX(50%);
    width: min(720px, 92vw);
    max-height: 86vh;
    background: var(--surface);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow-lg);
    z-index: 101;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
  }
  header h2 {
    margin: 0;
    font-size: 1.05rem;
  }
  .close {
    background: transparent;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    padding: 0.1rem 0.45rem;
    border-radius: var(--r-sm);
    color: var(--text-muted);
    cursor: pointer;
  }
  .close:hover {
    background: var(--surface-2);
    color: var(--text);
  }
  .toolbar {
    display: flex;
    gap: 0.55rem;
    padding: 0.85rem 1.25rem;
    border-bottom: 1px solid var(--border);
    align-items: center;
  }
  .toolbar .control {
    flex: 1;
  }
  .upload {
    cursor: pointer;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
    gap: 0.55rem;
    padding: 1.1rem 1.25rem;
    overflow-y: auto;
  }
  .cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 0.6rem 0.4rem 0.45rem;
    background:
      radial-gradient(120% 120% at 50% 0%, #16171c 0%, var(--device-bg) 70%);
    border: 2px solid transparent;
    border-radius: var(--r-md);
    cursor: pointer;
    transition:
      border-color 0.12s ease,
      box-shadow 0.12s ease;
  }
  .cell:hover {
    border-color: var(--device-edge);
  }
  .cell.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .cell img {
    width: 44px;
    height: 44px;
    object-fit: contain;
  }
  .cap {
    font-size: 0.72rem;
    color: #b9bcc6;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .state {
    color: var(--text-muted);
    padding: 2rem 1.25rem;
    text-align: center;
  }
  .error {
    color: var(--danger-strong);
    background: var(--danger-soft);
    margin: 0;
    padding: 0.6rem 1.25rem;
    font-size: 0.875rem;
  }
</style>
