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

  function pick(iconId: string) {
    onSelect(iconId);
  }

  function clearIcon() {
    onSelect(null);
  }
</script>

{#if open}
  <div
    class="backdrop"
    role="presentation"
    onclick={onClose}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
  ></div>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Icon picker">
    <header>
      <h2>Choose an icon</h2>
      <button type="button" class="close" onclick={onClose} aria-label="Close">×</button>
    </header>

    <div class="toolbar">
      <input
        type="search"
        placeholder="Search…"
        bind:value={search}
        autocomplete="off"
      />
      <label class="upload-button">
        Upload PNG/JPG
        <input
          bind:this={uploadInput}
          type="file"
          accept="image/png,image/jpeg"
          hidden
          onchange={handleUpload}
        />
      </label>
      <button type="button" class="secondary" onclick={clearIcon}>No icon</button>
    </div>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    {#if loading && allIcons.length === 0}
      <p class="muted">Loading…</p>
    {:else if filtered.length === 0}
      <p class="muted">No matching icons.</p>
    {:else}
      <div class="grid">
        {#each filtered as icon (icon.id)}
          <button
            type="button"
            class="cell"
            class:selected={icon.id === selectedIconId}
            onclick={() => pick(icon.id)}
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
    background: rgba(0, 0, 0, 0.4);
    z-index: 100;
  }
  .modal {
    position: fixed;
    inset: 5vh 10vw;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    z-index: 101;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid #eee;
  }
  header h2 {
    margin: 0;
    font-size: 1.125rem;
  }
  .close {
    background: transparent;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    padding: 0.25rem 0.5rem;
    color: #555;
  }
  .close:hover {
    color: #000;
  }
  .toolbar {
    display: flex;
    gap: 0.625rem;
    padding: 0.75rem 1.5rem;
    border-bottom: 1px solid #eee;
    align-items: center;
  }
  .toolbar input[type='search'] {
    flex: 1;
    padding: 0.4rem 0.625rem;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    font: inherit;
  }
  .upload-button {
    background: #1d1d1d;
    color: #fff;
    padding: 0.4rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.875rem;
    white-space: nowrap;
  }
  .upload-button:hover {
    background: #333;
  }
  .secondary {
    background: transparent;
    color: #444;
    border: 1px solid #d0d0d0;
    padding: 0.4rem 0.75rem;
    border-radius: 6px;
    font: inherit;
  }
  .secondary:hover {
    background: #f3f3f3;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 0.5rem;
    padding: 1rem 1.5rem;
    overflow-y: auto;
    flex: 1;
  }
  .cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem;
    background: #1d1d1d;
    border: 2px solid transparent;
    border-radius: 8px;
    cursor: pointer;
  }
  .cell:hover {
    border-color: #999;
  }
  .cell.selected {
    border-color: #4c8bf5;
    background: #232f47;
  }
  .cell img {
    width: 48px;
    height: 48px;
    object-fit: contain;
  }
  .cap {
    font-size: 0.75rem;
    color: #ccc;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .muted {
    color: #888;
    padding: 1rem 1.5rem;
  }
  .error {
    color: #b00020;
    padding: 0 1.5rem;
  }
</style>
