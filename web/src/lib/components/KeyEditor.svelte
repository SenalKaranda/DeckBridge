<script lang="ts">
  import { ApiError } from '$lib/api/client';
  import { icons as iconsApi, keys as keysApi } from '$lib/api/resources';
  import IconPicker from './IconPicker.svelte';
  import KeyPreview from './KeyPreview.svelte';

  import type {
    Key,
    Page,
    PressAction,
    PressActionType,
    StateSubscription,
  } from '$lib/api/types';
  import {
    defaultPressAction,
    defaultStateSubscription,
    emptyKey,
  } from '$lib/api/types';

  interface Props {
    pageId: string;
    slot: number;
    initial: Key | null;
    pages: Page[];
    onSaved: (key: Key) => void;
    onDeleted: () => void;
  }

  let { pageId, slot, initial, pages, onSaved, onDeleted }: Props = $props();

  // Form state. Initialized ONCE from the `initial` prop at mount time;
  // the parent uses `{#key (pageId, slot)}` to force a fresh remount when
  // the user clicks a different slot, so we never need a $effect-based
  // re-init. (An effect would also fire when the parent updates its
  // `keys` array after a successful save, which would wipe the saved
  // confirmation toast — see the editor +page.svelte for context.)
  //
  // svelte-ignore state_referenced_locally — capturing only the initial
  // values of these props is exactly what we want here (see above).
  //
  // $state.snapshot() unwraps the reactive Proxy that $props() puts
  // around `initial` so we can safely deep-copy it into our own $state.
  const initialData = initial ?? emptyKey(pageId, slot);
  let label = $state(initialData.label);
  let iconId = $state<string | null>(initialData.icon_id);
  let padding = $state(initialData.padding);

  let showIcon = $state(initialData.show_icon);
  let showLabel = $state(initialData.show_label);
  let bgColor = $state(initialData.bg_color);
  let bgImageId = $state<string | null>(initialData.bg_image_id);
  let labelColor = $state(initialData.label_color);
  // Color inputs require a string value, but `null` is the schema's
  // "no tint" sentinel. Track the toggle separately so we can preserve
  // the user's last picked color when they re-enable the tint.
  let iconTintEnabled = $state(initialData.icon_color !== null);
  let iconColor = $state(initialData.icon_color ?? '#FFFFFF');
  let fontSize = $state(initialData.font_size);
  let press = $state<PressAction>($state.snapshot(initialData.press) as PressAction);
  let stateEnabled = $state(initialData.state !== null);
  let stateSub = $state<StateSubscription>(
    initialData.state
      ? ($state.snapshot(initialData.state) as StateSubscription)
      : defaultStateSubscription(),
  );
  let mapRows = $state<{ value: string; iconId: string }[]>(
    initialData.state
      ? Object.entries(initialData.state.icon_map).map(([value, iconId]) => ({
          value,
          iconId,
        }))
      : [],
  );

  let saving = $state(false);
  let deleting = $state(false);
  let testing = $state(false);
  let message = $state<string | null>(null);
  let messageKind = $state<'success' | 'error' | 'info'>('info');

  // ---- live preview ----
  let iconUrl = $derived(iconId ? iconsApi.rawUrl(iconId) : null);
  let bgImageUrl = $derived(bgImageId ? iconsApi.rawUrl(bgImageId) : null);
  let previewIconColor = $derived(iconTintEnabled ? iconColor : null);
  let otherPages = $derived(pages.filter((p) => p.id !== pageId));

  // ---- icon picker (shared for foreground / background / state rows) ----
  type PickerTarget =
    | { kind: 'icon' }
    | { kind: 'bg' }
    | { kind: 'map'; index: number }
    | { kind: 'default' };

  let pickerOpen = $state(false);
  let pickerTarget = $state<PickerTarget>({ kind: 'icon' });

  function openPicker(target: PickerTarget) {
    pickerTarget = target;
    pickerOpen = true;
  }

  let pickerSelectedId = $derived.by(() => {
    switch (pickerTarget.kind) {
      case 'icon':
        return iconId;
      case 'bg':
        return bgImageId;
      case 'map':
        return mapRows[pickerTarget.index]?.iconId || null;
      case 'default':
        return stateSub.default_icon_id;
    }
  });

  function handlePick(id: string | null) {
    switch (pickerTarget.kind) {
      case 'icon':
        iconId = id;
        break;
      case 'bg':
        bgImageId = id;
        break;
      case 'map': {
        const i = pickerTarget.index;
        mapRows = mapRows.map((r, idx) => (idx === i ? { ...r, iconId: id ?? '' } : r));
        break;
      }
      case 'default':
        stateSub.default_icon_id = id;
        break;
    }
    pickerOpen = false;
  }

  // ---- press action options (friendly framing of the schema's types) ----
  const ACTION_OPTIONS: {
    type: PressActionType;
    title: string;
    desc: string;
  }[] = [
    { type: 'mqtt_publish', title: 'Send a command', desc: 'Publish an MQTT message' },
    { type: 'http_webhook', title: 'Call a web service', desc: 'Fire an HTTP request' },
    { type: 'page_switch', title: 'Switch page', desc: 'Jump to another page' },
    { type: 'no_op', title: 'Nothing', desc: 'Just a label or status' },
  ];

  const METHODS = ['GET', 'POST', 'PUT', 'DELETE'] as const;

  // Assigning inside the {#if press.type === 'http_webhook'} block from a
  // closure loses TS's control-flow narrowing of the `press` union, so the
  // type guard has to live in a function the assignment can narrow within.
  function setMethod(m: (typeof METHODS)[number]) {
    if (press.type === 'http_webhook') press.method = m;
  }

  function setActionType(t: PressActionType) {
    if (t === 'no_op') press = { type: 'no_op' };
    else if (t === 'mqtt_publish')
      press = { type: 'mqtt_publish', topic: '', payload: '', retain: false, qos: 0 };
    else if (t === 'http_webhook')
      press = { type: 'http_webhook', url: '', method: 'POST', headers: {}, body: '' };
    else if (t === 'page_switch') press = { type: 'page_switch', target_page_id: '' };
  }

  function addMapRow() {
    mapRows = [...mapRows, { value: '', iconId: '' }];
  }
  function removeMapRow(idx: number) {
    mapRows = mapRows.filter((_, i) => i !== idx);
  }

  function buildStatePayload(): StateSubscription | null {
    if (!stateEnabled) return null;
    const icon_map: Record<string, string> = {};
    for (const row of mapRows) {
      if (row.value && row.iconId) icon_map[row.value] = row.iconId;
    }
    return {
      topic: stateSub.topic,
      jmespath: stateSub.jmespath || null,
      icon_map,
      default_icon_id: stateSub.default_icon_id || null,
    };
  }

  function flash(text: string, kind: 'success' | 'error' | 'info') {
    message = text;
    messageKind = kind;
  }

  async function save() {
    saving = true;
    message = null;
    try {
      const saved = await keysApi.put(pageId, slot, {
        label,
        icon_id: iconId,
        press,
        state: buildStatePayload(),
        padding,
        show_icon: showIcon,
        show_label: showLabel,
        bg_color: bgColor,
        bg_image_id: bgImageId,
        label_color: labelColor,
        icon_color: iconTintEnabled ? iconColor : null,
        font_size: fontSize,
      });
      flash('Saved to your deck.', 'success');
      onSaved(saved);
    } catch (err) {
      flash(err instanceof ApiError ? err.detail : String(err), 'error');
    } finally {
      saving = false;
    }
  }

  async function testPress() {
    if (!initial) {
      flash('Save the key first, then try it.', 'info');
      return;
    }
    testing = true;
    message = null;
    try {
      const result = await keysApi.testPress(pageId, slot);
      flash(`Done — ${friendlyAction(result.action_type)} fired.`, 'success');
    } catch (err) {
      flash(err instanceof ApiError ? err.detail : String(err), 'error');
    } finally {
      testing = false;
    }
  }

  function friendlyAction(type: string): string {
    return (
      ACTION_OPTIONS.find((o) => o.type === type)?.title.toLowerCase() ?? 'the action'
    );
  }

  async function clearKey() {
    if (!initial) {
      // Nothing saved yet — just reset the form to empty defaults.
      const blank = emptyKey(pageId, slot);
      label = blank.label;
      iconId = blank.icon_id;
      padding = blank.padding;
      showIcon = blank.show_icon;
      showLabel = blank.show_label;
      bgColor = blank.bg_color;
      bgImageId = blank.bg_image_id;
      labelColor = blank.label_color;
      iconTintEnabled = false;
      iconColor = '#FFFFFF';
      fontSize = blank.font_size;
      press = defaultPressAction();
      stateEnabled = false;
      stateSub = defaultStateSubscription();
      mapRows = [];
      flash('Form reset.', 'info');
      return;
    }
    if (!confirm('Clear this key? It will be removed from the deck.')) return;
    deleting = true;
    message = null;
    try {
      await keysApi.remove(pageId, slot);
      onDeleted();
    } catch (err) {
      flash(err instanceof ApiError ? err.detail : String(err), 'error');
    } finally {
      deleting = false;
    }
  }

  let busy = $derived(saving || deleting || testing);
</script>

{#snippet actionIcon(type: PressActionType)}
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    {#if type === 'mqtt_publish'}
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />
    {:else if type === 'http_webhook'}
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3c2.5 2.5 3.5 5.6 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.6-3.5-9s1-6.5 3.5-9Z" />
    {:else if type === 'page_switch'}
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    {:else}
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    {/if}
  </svg>
{/snippet}

<div class="editor card">
  <!-- Live preview header -->
  <div class="head">
    <div class="head-preview">
      <KeyPreview
        {label}
        {iconUrl}
        {bgImageUrl}
        {showIcon}
        {showLabel}
        {bgColor}
        {labelColor}
        iconColor={previewIconColor}
        {fontSize}
        {padding}
        size={104}
      />
    </div>
    <div class="head-meta">
      <h2>{label.trim() || `Key ${slot + 1}`}</h2>
      <p class="muted small">{initial ? 'Editing' : 'Setting up'} key {slot + 1}</p>
    </div>
  </div>

  <!-- LOOK -->
  <section class="group">
    <h3 class="group-title">Look</h3>

    <div class="field">
      <label class="field-label" for="key-label">Label</label>
      <input
        id="key-label"
        class="control"
        bind:value={label}
        maxlength="32"
        placeholder="e.g. Kitchen"
      />
    </div>

    <div class="field">
      <div class="label-row">
        <span class="field-label">Icon</span>
        <label class="switch">
          <input type="checkbox" bind:checked={showIcon} />
          <span class="track"><span class="thumb"></span></span>
          <span class="switch-text">Show</span>
        </label>
      </div>
      <div class="picker-row">
        <button
          type="button"
          class="icon-pick"
          onclick={() => openPicker({ kind: 'icon' })}
          aria-label="Choose icon"
        >
          {#if iconUrl}
            <img src={iconUrl} alt="" />
          {:else}
            <span class="plus">+</span>
          {/if}
        </button>
        <div class="picker-actions">
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            onclick={() => openPicker({ kind: 'icon' })}
          >
            {iconId ? 'Change…' : 'Choose icon…'}
          </button>
          {#if iconId}
            <button
              type="button"
              class="btn btn--subtle btn--sm"
              onclick={() => (iconId = null)}
            >
              Remove
            </button>
          {/if}
        </div>
      </div>
    </div>

    <div class="field">
      <span class="field-label">Background</span>
      <div class="bg-row">
        <input
          type="color"
          class="swatch"
          bind:value={bgColor}
          aria-label="Background color"
        />
        <span class="hexcode">{bgColor}</span>
        <span class="spacer"></span>
        <button
          type="button"
          class="btn btn--ghost btn--sm"
          onclick={() => openPicker({ kind: 'bg' })}
        >
          {bgImageId ? 'Change image…' : 'Add image…'}
        </button>
        {#if bgImageId}
          <button
            type="button"
            class="btn btn--subtle btn--sm"
            onclick={() => (bgImageId = null)}
          >
            Remove
          </button>
        {/if}
      </div>
    </div>

    <details class="adv">
      <summary>Fine-tune appearance</summary>
      <div class="adv-body">
        <label class="switch">
          <input type="checkbox" bind:checked={showLabel} />
          <span class="track"><span class="thumb"></span></span>
          <span class="switch-text">Show label</span>
        </label>

        <div class="field">
          <span class="field-label">Label color</span>
          <div class="color-inline">
            <input
              type="color"
              class="swatch"
              bind:value={labelColor}
              aria-label="Label color"
            />
            <span class="hexcode">{labelColor}</span>
          </div>
        </div>

        <div class="field">
          <span class="field-label">Label size <span class="val">{fontSize}px</span></span>
          <input type="range" min="8" max="32" step="1" bind:value={fontSize} />
        </div>

        {#if showIcon}
          <div class="field">
            <label class="switch">
              <input type="checkbox" bind:checked={iconTintEnabled} />
              <span class="track"><span class="thumb"></span></span>
              <span class="switch-text">Tint icon</span>
            </label>
            {#if iconTintEnabled}
              <div class="color-inline">
                <input
                  type="color"
                  class="swatch"
                  bind:value={iconColor}
                  aria-label="Icon tint color"
                />
                <span class="hexcode">{iconColor}</span>
              </div>
            {/if}
            <p class="help">Recolors the icon. Looks best on the bundled white icons.</p>
          </div>
        {/if}

        <div class="field">
          <span class="field-label">Padding <span class="val">{padding}px</span></span>
          <input type="range" min="0" max="20" step="1" bind:value={padding} />
          <p class="help">Extra space around the icon and label.</p>
        </div>
      </div>
    </details>
  </section>

  <!-- WHEN PRESSED -->
  <section class="group">
    <h3 class="group-title">When pressed</h3>
    <div class="actions-grid">
      {#each ACTION_OPTIONS as opt (opt.type)}
        <button
          type="button"
          class="action-card"
          class:active={press.type === opt.type}
          onclick={() => setActionType(opt.type)}
        >
          <span class="action-ico">{@render actionIcon(opt.type)}</span>
          <span class="action-txt">
            <strong>{opt.title}</strong>
            <small>{opt.desc}</small>
          </span>
        </button>
      {/each}
    </div>

    {#if press.type === 'mqtt_publish'}
      <div class="detail">
        <div class="field">
          <label class="field-label" for="mq-topic">Topic</label>
          <input
            id="mq-topic"
            class="control"
            bind:value={press.topic}
            placeholder="home/kitchen/light/set"
          />
          <p class="help">Where the message is published.</p>
        </div>
        <div class="field">
          <label class="field-label" for="mq-payload">Message</label>
          <input
            id="mq-payload"
            class="control"
            bind:value={press.payload}
            placeholder="ON · TOGGLE · or JSON"
          />
          <p class="help">What to send. Plain text or a JSON string.</p>
        </div>
        <details class="adv">
          <summary>Advanced</summary>
          <div class="adv-body">
            <label class="switch">
              <input type="checkbox" bind:checked={press.retain} />
              <span class="track"><span class="thumb"></span></span>
              <span class="switch-text">Retain last message on the broker</span>
            </label>
            <div class="field">
              <label class="field-label" for="mq-qos">Quality of service</label>
              <select id="mq-qos" class="control" bind:value={press.qos}>
                <option value={0}>0 — at most once</option>
                <option value={1}>1 — at least once</option>
                <option value={2}>2 — exactly once</option>
              </select>
            </div>
          </div>
        </details>
      </div>
    {:else if press.type === 'http_webhook'}
      <div class="detail">
        <div class="field">
          <label class="field-label" for="hk-url">Address</label>
          <input
            id="hk-url"
            class="control"
            bind:value={press.url}
            placeholder="http://host:port/path"
          />
        </div>
        <div class="field">
          <span class="field-label">Method</span>
          <div class="segmented">
            {#each METHODS as m (m)}
              <button
                type="button"
                class:active={press.method === m}
                onclick={() => setMethod(m)}
              >
                {m}
              </button>
            {/each}
          </div>
        </div>
        {#if press.method === 'POST' || press.method === 'PUT'}
          <div class="field">
            <label class="field-label" for="hk-body">Body</label>
            <textarea id="hk-body" class="control mono" bind:value={press.body} rows="3"
            ></textarea>
            <p class="help">Sent with POST and PUT requests.</p>
          </div>
        {/if}
      </div>
    {:else if press.type === 'page_switch'}
      <div class="detail">
        <div class="field">
          <label class="field-label" for="ps-target">Go to page</label>
          <select id="ps-target" class="control" bind:value={press.target_page_id}>
            <option value="" disabled>Choose a page…</option>
            {#each otherPages as p (p.id)}
              <option value={p.id}>{p.name || 'Untitled page'}</option>
            {/each}
          </select>
          {#if otherPages.length === 0}
            <p class="help">There are no other pages yet — add one to switch to it.</p>
          {/if}
        </div>
      </div>
    {:else}
      <p class="help detail-note">
        This key won't do anything when pressed — useful as a label or a live
        status indicator.
      </p>
    {/if}
  </section>

  <!-- LIVE STATUS -->
  <section class="group">
    <div class="group-head">
      <div>
        <h3 class="group-title flush">Live status</h3>
        <p class="help">Switch this key's icon automatically based on an MQTT topic.</p>
      </div>
      <label class="switch">
        <input type="checkbox" bind:checked={stateEnabled} />
        <span class="track"><span class="thumb"></span></span>
      </label>
    </div>

    {#if stateEnabled}
      <div class="detail">
        <div class="field">
          <label class="field-label" for="st-topic">Status topic</label>
          <input
            id="st-topic"
            class="control"
            bind:value={stateSub.topic}
            placeholder="home/kitchen/light/state"
          />
        </div>

        <div class="field">
          <span class="field-label">Icon for each value</span>
          <p class="help">Pick an icon to show when a specific value comes in.</p>
          {#each mapRows as row, i (i)}
            <div class="map-row">
              <input class="control" placeholder="Value, e.g. on" bind:value={row.value} />
              <button
                type="button"
                class="icon-pick sm"
                onclick={() => openPicker({ kind: 'map', index: i })}
                aria-label="Choose icon for this value"
              >
                {#if row.iconId}
                  <img src={iconsApi.rawUrl(row.iconId)} alt="" />
                {:else}
                  <span class="plus">+</span>
                {/if}
              </button>
              <button
                type="button"
                class="btn btn--icon btn--subtle"
                onclick={() => removeMapRow(i)}
                aria-label="Remove value"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
                </svg>
              </button>
            </div>
          {/each}
          <button type="button" class="btn btn--ghost btn--sm add-row" onclick={addMapRow}>
            + Add value
          </button>
        </div>

        <div class="field">
          <span class="field-label">Fallback icon</span>
          <p class="help">Shown when the value doesn't match any above.</p>
          <button
            type="button"
            class="icon-pick"
            onclick={() => openPicker({ kind: 'default' })}
            aria-label="Choose fallback icon"
          >
            {#if stateSub.default_icon_id}
              <img src={iconsApi.rawUrl(stateSub.default_icon_id)} alt="" />
            {:else}
              <span class="plus">+</span>
            {/if}
          </button>
        </div>

        <details class="adv">
          <summary>Advanced</summary>
          <div class="adv-body">
            <div class="field">
              <label class="field-label" for="st-path">Read value from JSON</label>
              <input
                id="st-path"
                class="control mono"
                bind:value={stateSub.jmespath}
                placeholder="state.power"
              />
              <p class="help">
                Optional JMESPath for JSON payloads — e.g. <code>state.power</code>.
              </p>
            </div>
          </div>
        </details>
      </div>
    {/if}
  </section>

  <!-- FOOTER -->
  <div class="foot">
    <div class="foot-msg" aria-live="polite">
      {#if message}
        <span class="toast toast--{messageKind}">{message}</span>
      {/if}
    </div>
    <div class="foot-btns">
      <button type="button" class="btn btn--danger" onclick={clearKey} disabled={busy}>
        {deleting ? 'Clearing…' : initial ? 'Clear key' : 'Reset'}
      </button>
      <button
        type="button"
        class="btn btn--ghost"
        onclick={testPress}
        disabled={busy || !initial}
        title={initial
          ? 'Fire the action now without pressing the physical key'
          : 'Save the key first to try it'}
      >
        {testing ? 'Testing…' : 'Test'}
      </button>
      <button type="button" class="btn btn--primary" onclick={save} disabled={busy}>
        {saving ? 'Saving…' : 'Save key'}
      </button>
    </div>
  </div>
</div>

<IconPicker
  open={pickerOpen}
  selectedIconId={pickerSelectedId}
  onSelect={handlePick}
  onClose={() => (pickerOpen = false)}
/>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
  }

  /* ---- header with live preview ---- */
  .head {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.1rem 1.25rem;
    background: linear-gradient(180deg, var(--surface-2), var(--surface));
    border-bottom: 1px solid var(--border);
  }
  .head-preview {
    width: 104px;
    height: 104px;
    flex: none;
    padding: 8px;
    border-radius: var(--r-lg);
    background:
      radial-gradient(120% 120% at 50% 0%, #16171c 0%, var(--device-bg) 70%);
    box-shadow: var(--shadow-sm);
  }
  .head-meta h2 {
    margin: 0;
    font-size: 1.15rem;
    word-break: break-word;
  }
  .small {
    font-size: 0.85rem;
  }

  /* ---- sections ---- */
  .group {
    padding: 1.1rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }
  .group-title {
    margin: 0;
    font-size: 0.78rem;
    font-weight: 650;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-faint);
  }
  .group-title.flush {
    margin: 0;
  }
  .group-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  .group-head .help {
    margin-top: 0.15rem;
  }

  .label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .val {
    color: var(--text-muted);
    font-weight: 500;
  }

  /* ---- icon picker button ---- */
  .picker-row {
    display: flex;
    align-items: center;
    gap: 0.85rem;
  }
  .picker-actions {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .icon-pick {
    width: 52px;
    height: 52px;
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    background:
      radial-gradient(120% 120% at 50% 0%, #16171c 0%, var(--device-bg) 70%);
    border: 1px solid var(--device-edge);
    border-radius: var(--r-md);
    cursor: pointer;
    overflow: hidden;
    transition:
      border-color 0.12s ease,
      box-shadow 0.12s ease;
  }
  .icon-pick.sm {
    width: 42px;
    height: 42px;
  }
  .icon-pick:hover {
    border-color: var(--accent);
  }
  .icon-pick:focus-visible {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .icon-pick img {
    width: 72%;
    height: 72%;
    object-fit: contain;
  }
  .icon-pick .plus {
    color: #5a5e6b;
    font-size: 1.3rem;
    font-weight: 300;
  }

  /* ---- color swatch + hex ---- */
  .bg-row,
  .color-inline {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .spacer {
    flex: 1;
  }
  .swatch {
    width: 2.3rem;
    height: 2.3rem;
    flex: none;
    padding: 0;
    border: 1px solid var(--border-strong);
    border-radius: var(--r-sm);
    background: none;
    cursor: pointer;
  }
  .swatch::-webkit-color-swatch-wrapper {
    padding: 3px;
  }
  .swatch::-webkit-color-swatch {
    border: none;
    border-radius: 4px;
  }
  .hexcode {
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.82rem;
    color: var(--text-muted);
    text-transform: uppercase;
  }

  /* ---- advanced disclosure ---- */
  .adv {
    border-top: 1px dashed var(--border);
    padding-top: 0.5rem;
  }
  .adv > summary {
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 550;
    color: var(--accent);
    list-style: none;
    padding: 0.15rem 0;
    user-select: none;
  }
  .adv > summary::-webkit-details-marker {
    display: none;
  }
  .adv > summary::before {
    content: '▸';
    display: inline-block;
    margin-right: 0.4rem;
    transition: transform 0.12s ease;
    font-size: 0.7rem;
  }
  .adv[open] > summary::before {
    transform: rotate(90deg);
  }
  .adv-body {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding-top: 0.75rem;
  }

  /* ---- action cards ---- */
  .actions-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
  }
  .action-card {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    text-align: left;
    padding: 0.7rem 0.8rem;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--r-md);
    cursor: pointer;
    transition:
      border-color 0.12s ease,
      background 0.12s ease,
      box-shadow 0.12s ease;
  }
  .action-card:hover {
    border-color: var(--accent);
  }
  .action-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 1px var(--accent);
  }
  .action-ico {
    flex: none;
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    color: var(--text-muted);
  }
  .action-card.active .action-ico {
    background: #fff;
    color: var(--accent);
  }
  .action-ico svg {
    width: 19px;
    height: 19px;
  }
  .action-txt {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }
  .action-txt strong {
    font-weight: 600;
    font-size: 0.92rem;
  }
  .action-txt small {
    color: var(--text-muted);
    font-size: 0.78rem;
  }

  /* ---- per-action detail ---- */
  .detail {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding: 0.95rem;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
  }
  .detail-note {
    margin: 0;
    padding: 0.4rem 0.1rem 0;
  }
  .mono {
    font-family: ui-monospace, 'Cascadia Code', monospace;
    font-size: 0.86rem;
  }

  /* segmented control (HTTP method) */
  .segmented {
    display: inline-flex;
    background: var(--surface-3);
    border-radius: var(--r-sm);
    padding: 3px;
    gap: 3px;
    align-self: flex-start;
  }
  .segmented button {
    border: none;
    background: transparent;
    padding: 0.32rem 0.7rem;
    border-radius: 5px;
    font: inherit;
    font-size: 0.82rem;
    font-weight: 550;
    color: var(--text-muted);
    cursor: pointer;
  }
  .segmented button.active {
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow-sm);
  }

  /* state value→icon rows */
  .map-row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.5rem;
    align-items: center;
  }
  .add-row {
    align-self: flex-start;
  }

  code {
    background: var(--surface-3);
    padding: 0.05rem 0.3rem;
    border-radius: 4px;
    font-size: 0.85em;
  }

  /* range inputs */
  input[type='range'] {
    width: 100%;
    accent-color: var(--accent);
  }

  /* ---- footer ---- */
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.9rem 1.25rem;
    background: var(--surface-2);
    flex-wrap: wrap;
  }
  .foot-msg {
    flex: 1;
    min-width: 0;
  }
  .toast {
    display: inline-block;
    padding: 0.35rem 0.6rem;
    border-radius: var(--r-sm);
    font-size: 0.85rem;
    font-weight: 500;
  }
  .toast--success {
    background: var(--success-soft);
    color: var(--success);
  }
  .toast--error {
    background: var(--danger-soft);
    color: var(--danger-strong);
  }
  .toast--info {
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .foot-btns {
    display: flex;
    gap: 0.5rem;
  }
</style>
