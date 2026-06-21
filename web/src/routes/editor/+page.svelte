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
  let deckModel = $state<string>('');
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
  let connected = $derived(deckSerial !== FALLBACK_SERIAL);

  // ---- lifecycle ----

  onMount(async () => {
    try {
      const status = await statusApi.get();
      deckSerial = status.decks[0]?.serial ?? FALLBACK_SERIAL;
      deckModel = status.decks[0]?.model ?? '';
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
    renamingPage = false;
    keys = await keysApi.listForPage(id);
    pageName = pages.find((p) => p.id === id)?.name ?? '';
  }

  async function createPage() {
    const fresh = await pagesApi.create({
      deck_serial: deckSerial,
      name: `Page ${pages.length + 1}`,
      order: pages.length,
    });
    pages = [...pages, fresh];
    await selectPage(fresh.id);
  }

  function startRename() {
    if (!activePage) return;
    pageName = activePage.name;
    renamingPage = true;
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
        `Delete "${activePage.name || 'this page'}"? Its keys are deleted too. This can't be undone.`,
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

  // Focus a node as soon as it mounts (used for the inline rename input).
  function autofocus(node: HTMLElement) {
    node.focus();
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
    selectedSlot = null;
  }
</script>

<div class="wrap">
  <header class="page-header">
    <div>
      <h1>Your deck</h1>
      <p class="muted sub">Click a key to set up what it shows and does.</p>
    </div>
    <span
      class="chip status"
      class:ok={connected}
      title={connected ? `Serial ${deckSerial}` : 'Pages bind to your deck automatically once it’s plugged in.'}
    >
      <span class="dot"></span>
      {connected ? deckModel || 'Stream Deck connected' : 'No deck connected'}
    </span>
  </header>

  {#if error}
    <p class="error card">{error}</p>
  {:else if loading}
    <p class="muted loading">Loading…</p>
  {:else}
    <!-- Page switcher -->
    <div class="pagebar">
      <div class="tabs" role="tablist">
        {#each pages as page (page.id)}
          <button
            type="button"
            role="tab"
            aria-selected={page.id === activePageId}
            class="tab"
            class:active={page.id === activePageId}
            onclick={() => selectPage(page.id)}
          >
            {page.name || 'Untitled page'}
          </button>
        {/each}
        <button type="button" class="tab add" onclick={createPage} title="Add a page">
          + Page
        </button>
      </div>

      {#if activePage}
        <div class="page-tools">
          {#if renamingPage}
            <input
              class="control rename"
              bind:value={pageName}
              placeholder="Page name"
              onkeydown={(e) => {
                if (e.key === 'Enter') renamePage();
                if (e.key === 'Escape') renamingPage = false;
              }}
              use:autofocus
            />
            <button type="button" class="btn btn--primary btn--sm" onclick={renamePage}>
              Save
            </button>
            <button
              type="button"
              class="btn btn--subtle btn--sm"
              onclick={() => (renamingPage = false)}
            >
              Cancel
            </button>
          {:else}
            <button
              type="button"
              class="btn btn--subtle btn--sm"
              onclick={startRename}
              title="Rename page"
            >
              Rename
            </button>
            <button
              type="button"
              class="btn btn--danger btn--sm"
              onclick={deletePage}
              title="Delete page"
            >
              Delete
            </button>
          {/if}
        </div>
      {/if}
    </div>

    <div class="layout">
      <section class="device-panel">
        {#if activePage}
          <DeckGrid {keys} {selectedSlot} onSlotClick={handleSlotClick} />
          <p class="device-caption">Live preview — matches what's on the device.</p>
        {:else}
          <div class="empty card">
            <p class="muted">No pages yet for this deck.</p>
            <button type="button" class="btn btn--primary" onclick={createPage}>
              Create your first page
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
          <div class="hint card">
            <div class="hint-art" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <path d="M7 9h.01M12 9h.01M17 9h.01M7 14h.01M12 14h5" />
              </svg>
            </div>
            <h3>Pick a key to begin</h3>
            <p class="muted">
              Select any key on the left, then give it a label, an icon, and an
              action.
            </p>
          </div>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .wrap {
    max-width: 72rem;
    margin: 1.75rem auto;
    padding: 0 1.5rem 4rem;
  }
  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  h1 {
    margin: 0 0 0.2rem;
    font-size: 1.6rem;
  }
  .sub {
    margin: 0;
  }
  .error {
    color: var(--danger-strong);
    background: var(--danger-soft);
    border-color: transparent;
    padding: 1rem 1.25rem;
  }
  .loading {
    padding: 2rem 0;
  }

  /* status chip */
  .status {
    white-space: nowrap;
  }
  .status .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
  }
  .status.ok {
    background: var(--success-soft);
    color: var(--success);
    border-color: transparent;
  }
  .status.ok .dot {
    background: var(--success);
  }

  /* page bar */
  .pagebar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.25rem;
    flex-wrap: wrap;
  }
  .tabs {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
  }
  .tab {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 999px;
    padding: 0.4rem 0.9rem;
    font: inherit;
    font-weight: 550;
    font-size: 0.9rem;
    color: var(--text-muted);
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease,
      border-color 0.12s ease;
  }
  .tab:hover {
    background: var(--surface-2);
    color: var(--text);
  }
  .tab.active {
    background: var(--text);
    color: var(--surface);
  }
  .tab.add {
    color: var(--accent);
  }
  .tab.add:hover {
    background: var(--accent-soft);
    color: var(--accent-strong);
  }
  .page-tools {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .rename {
    width: 12rem;
  }

  /* layout */
  .layout {
    display: grid;
    grid-template-columns: minmax(260px, 340px) 1fr;
    gap: 1.5rem;
    align-items: start;
  }
  @media (max-width: 920px) {
    .layout {
      grid-template-columns: 1fr;
    }
    .device-panel {
      position: static !important;
    }
  }
  .device-panel {
    position: sticky;
    top: 1rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.7rem;
  }
  .device-caption {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-faint);
    text-align: center;
  }
  .editor-pane {
    min-width: 0;
  }

  .empty {
    padding: 2.5rem 1.5rem;
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    align-items: center;
    width: 100%;
  }

  .hint {
    padding: 3rem 2rem;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
  }
  .hint-art {
    width: 56px;
    height: 56px;
    display: grid;
    place-items: center;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: var(--r-lg);
    margin-bottom: 0.6rem;
  }
  .hint-art svg {
    width: 30px;
    height: 30px;
  }
  .hint h3 {
    margin: 0;
  }
  .hint p {
    margin: 0;
    max-width: 22rem;
  }
</style>
