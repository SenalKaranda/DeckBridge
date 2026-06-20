<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError } from '$lib/api/client';
  import {
    keys as keysApi,
    pages as pagesApi,
    status as statusApi,
  } from '$lib/api/resources';
  import DeckGrid from '$lib/components/DeckGrid.svelte';
  import KeyEditor from '$lib/components/KeyEditor.svelte';

  import type { Key, Page } from '$lib/api/types';

  // ---- state ----

  // We pin the editor to one deck. v1 always picks the first attached deck;
  // if no deck is attached we fall back to "default" so the user can still
  // build pages and have them auto-bind when a deck appears later.
  const FALLBACK_SERIAL = 'default';

  let deckSerial = $state<string>(FALLBACK_SERIAL);
  let pages = $state<Page[]>([]);
  let activePageId = $state<string | null>(null);
  let keys = $state<Key[]>([]);
  let selectedSlot = $state<number | null>(null);

  let loading = $state(true);
  let error = $state<string | null>(null);
  let renamingPage = $state(false);
  let pageName = $state('');

  let activePage = $derived(pages.find((p) => p.id === activePageId) ?? null);
  let selectedKey = $derived(
    selectedSlot !== null ? (keys.find((k) => k.slot === selectedSlot) ?? null) : null,
  );

  // ---- lifecycle ----

  onMount(async () => {
    try {
      const status = await statusApi.get();
      deckSerial = status.decks[0]?.serial ?? FALLBACK_SERIAL;
      await loadPages();
    } catch (err) {
      error = err instanceof ApiError ? err.detail : String(err);
    } finally {
      loading = false;
    }
  });

  async function loadPages() {
    pages = await pagesApi.list(deckSerial);
    if (pages.length > 0 && !pages.some((p) => p.id === activePageId)) {
      await selectPage(pages[0].id);
    } else if (pages.length === 0) {
      activePageId = null;
      keys = [];
    }
  }

  async function selectPage(id: string) {
    activePageId = id;
    selectedSlot = null;
    keys = await keysApi.listForPage(id);
    pageName = pages.find((p) => p.id === id)?.name ?? '';
  }

  async function createPage() {
    const fresh = await pagesApi.create({
      deck_serial: deckSerial,
      name: 'New page',
      order: pages.length,
    });
    pages = [...pages, fresh];
    await selectPage(fresh.id);
  }

  async function renamePage() {
    if (!activePage) return;
    const updated = await pagesApi.patch(activePage.id, { name: pageName });
    pages = pages.map((p) => (p.id === updated.id ? updated : p));
    renamingPage = false;
  }

  async function deletePage() {
    if (!activePage) return;
    if (
      !confirm(
        `Delete page "${activePage.name || activePage.id.slice(0, 8)}"? Keys on it are also deleted.`,
      )
    ) {
      return;
    }
    const removedId = activePage.id;
    await pagesApi.remove(removedId);
    activePageId = null;
    pages = pages.filter((p) => p.id !== removedId);
    if (pages.length > 0) await selectPage(pages[0].id);
    else keys = [];
  }

  function handleSlotClick(slot: number) {
    selectedSlot = slot;
  }

  function handleKeySaved(saved: Key) {
    keys = [...keys.filter((k) => k.slot !== saved.slot), saved].sort(
      (a, b) => a.slot - b.slot,
    );
  }

  function handleKeyDeleted() {
    if (selectedSlot === null) return;
    const wasSlot = selectedSlot;
    keys = keys.filter((k) => k.slot !== wasSlot);
  }
</script>

<div class="wrap">
  <header class="page-header">
    <div>
      <h1>Editor</h1>
      <p class="muted">
        Deck: <code>{deckSerial}</code>
        {#if deckSerial === FALLBACK_SERIAL}
          <span class="badge"
            >no deck attached — pages here will bind to <code>default</code></span
          >
        {/if}
      </p>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {:else if loading}
    <p class="muted">Loading…</p>
  {:else}
    <div class="page-tabs">
      {#each pages as page (page.id)}
        <button
          type="button"
          class:active={page.id === activePageId}
          onclick={() => selectPage(page.id)}
        >
          {page.name || '(unnamed)'}
        </button>
      {/each}
      <button type="button" class="add" onclick={createPage}>+ Page</button>
    </div>

    {#if activePage}
      <div class="page-controls">
        {#if renamingPage}
          <input
            bind:value={pageName}
            placeholder="Page name"
            onkeydown={(e) => e.key === 'Enter' && renamePage()}
          />
          <button type="button" onclick={renamePage}>Save</button>
          <button type="button" class="link" onclick={() => (renamingPage = false)}>
            Cancel
          </button>
        {:else}
          <span class="muted">Page id <code>{activePage.id.slice(0, 8)}…</code></span>
          <button type="button" class="link" onclick={() => (renamingPage = true)}>
            Rename
          </button>
          <button type="button" class="link danger" onclick={deletePage}>Delete</button>
        {/if}
      </div>
    {/if}

    <div class="layout">
      <section class="grid-pane">
        {#if activePage}
          <DeckGrid {keys} {selectedSlot} onSlotClick={handleSlotClick} />
        {:else}
          <div class="empty">
            <p class="muted">No pages yet for this deck.</p>
            <button type="button" class="primary" onclick={createPage}>
              Create the first page
            </button>
          </div>
        {/if}
      </section>

      <section class="editor-pane">
        {#if activePage && selectedSlot !== null}
          <!--
            Key the editor on (page, slot) so switching slots fully remounts
            the component. KeyEditor's form fields are $state initialized
            from the `initial` prop ONCE at mount; without the {#key} block
            an effect-based re-init would also wipe the user's "Saved."
            confirmation message every time the parent updates `keys` in
            response to a successful save.
          -->
          {#key `${activePage.id}:${selectedSlot}`}
            <KeyEditor
              pageId={activePage.id}
              slot={selectedSlot}
              initial={selectedKey}
              {pages}
              onSaved={handleKeySaved}
              onDeleted={handleKeyDeleted}
            />
          {/key}
        {:else if activePage}
          <p class="muted hint">Click a slot in the grid to edit it.</p>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .wrap {
    max-width: 76rem;
    margin: 1.5rem auto;
    padding: 0 1.5rem 4rem;
  }
  .page-header {
    margin-bottom: 1rem;
  }
  h1 {
    margin: 0 0 0.125rem;
  }
  .muted {
    color: #666;
    margin: 0;
  }
  .error {
    color: #b00020;
  }
  .badge {
    display: inline-block;
    background: #fff3cd;
    color: #856404;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8125rem;
    margin-left: 0.5rem;
  }
  .page-tabs {
    display: flex;
    gap: 0.25rem;
    margin-bottom: 0.625rem;
    border-bottom: 1px solid #ddd;
    padding-bottom: 0.25rem;
    flex-wrap: wrap;
  }
  .page-tabs button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px 6px 0 0;
    padding: 0.4rem 0.75rem;
    font: inherit;
    color: #444;
    cursor: pointer;
  }
  .page-tabs button:hover {
    background: #ececec;
  }
  .page-tabs button.active {
    background: #fff;
    border-color: #ddd;
    border-bottom-color: #fff;
    color: #111;
    margin-bottom: -1px;
  }
  .page-tabs .add {
    color: #4c8bf5;
  }
  .page-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    color: #555;
    font-size: 0.875rem;
  }
  .page-controls input {
    padding: 0.3rem 0.5rem;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    font: inherit;
  }
  .page-controls button {
    background: #1d1d1d;
    color: #fff;
    border: none;
    padding: 0.3rem 0.625rem;
    border-radius: 6px;
    font: inherit;
  }
  .link {
    background: transparent !important;
    color: #4c8bf5 !important;
    border: none !important;
    padding: 0.125rem 0.375rem !important;
    cursor: pointer;
  }
  .link:hover {
    text-decoration: underline;
  }
  .link.danger {
    color: #b00020 !important;
  }
  .layout {
    display: grid;
    grid-template-columns: minmax(300px, 30rem) 1fr;
    gap: 1.5rem;
    align-items: start;
  }
  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
  .grid-pane {
    display: flex;
    justify-content: center;
  }
  .editor-pane {
    min-width: 0;
  }
  .empty {
    background: #fff;
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
    border: 1px dashed #ccc;
  }
  .primary {
    background: #1d1d1d;
    color: #fff;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    margin-top: 0.5rem;
  }
  .hint {
    background: #fafafa;
    border: 1px dashed #ddd;
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
  }
  code {
    background: #f0f0f0;
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-size: 0.95em;
  }
</style>
