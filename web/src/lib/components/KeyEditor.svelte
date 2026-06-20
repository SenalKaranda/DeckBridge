<script lang="ts">
  import { ApiError } from '$lib/api/client';
  import { icons as iconsApi, keys as keysApi } from '$lib/api/resources';
  import IconPicker from './IconPicker.svelte';

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
  // `keys` array after a successful save, which would wipe the "Saved."
  // confirmation message — see the editor +page.svelte for context.)
  //
  // svelte-ignore state_referenced_locally — capturing only the initial
  // values of these props is exactly what we want here (see above).
  //
  // $state.snapshot() unwraps the reactive Proxy that $props() puts
  // around `initial` so we can safely deep-copy it into our own $state.
  // structuredClone(proxy) throws "Proxy object could not be cloned",
  // which previously aborted KeyEditor's script for any non-empty slot
  // and left the form half-initialized + non-interactive.
  const initialData = initial ?? emptyKey(pageId, slot);
  let label = $state(initialData.label);
  let iconId = $state<string | null>(initialData.icon_id);
  let padding = $state(initialData.padding);

  // v1.1 presentation knobs.
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
  let pickerOpen = $state(false);
  // The IconPicker is reused for both foreground and background image
  // selection; this flag tells onSelect which target to update.
  let pickerTarget = $state<'icon' | 'bg'>('icon');

  function openPickerFor(target: 'icon' | 'bg') {
    pickerTarget = target;
    pickerOpen = true;
  }

  function setActionType(t: PressActionType) {
    if (t === 'no_op') press = { type: 'no_op' };
    else if (t === 'mqtt_publish')
      press = { type: 'mqtt_publish', topic: '', payload: '', retain: false, qos: 0 };
    else if (t === 'http_webhook')
      press = {
        type: 'http_webhook',
        url: '',
        method: 'POST',
        headers: {},
        body: '',
      };
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
      message = 'Saved.';
      onSaved(saved);
    } catch (err) {
      message = err instanceof ApiError ? err.detail : String(err);
    } finally {
      saving = false;
    }
  }

  async function testPress() {
    if (!initial) {
      message = 'Save the key first, then test it.';
      return;
    }
    testing = true;
    message = null;
    try {
      const result = await keysApi.testPress(pageId, slot);
      message = `Test fired (${result.action_type}) on deck ${result.deck_serial}.`;
    } catch (err) {
      message = err instanceof ApiError ? err.detail : String(err);
    } finally {
      testing = false;
    }
  }

  async function clearKey() {
    if (!initial) {
      // Nothing to delete; just reset the form.
      label = '';
      iconId = null;
      padding = 0;
      showIcon = true;
      showLabel = true;
      bgColor = '#000000';
      bgImageId = null;
      labelColor = '#FFFFFF';
      iconTintEnabled = false;
      iconColor = '#FFFFFF';
      fontSize = 14;
      press = defaultPressAction();
      stateEnabled = false;
      mapRows = [];
      return;
    }
    deleting = true;
    message = null;
    try {
      await keysApi.remove(pageId, slot);
      onDeleted();
    } catch (err) {
      message = err instanceof ApiError ? err.detail : String(err);
    } finally {
      deleting = false;
    }
  }
</script>

<div class="editor">
  <header>
    <h2>Slot {slot}</h2>
    <span class="muted">{initial ? 'Edit' : 'Empty — fill out below to configure'}</span>
  </header>

  <div class="grid">
    <label class="full">
      <span>Label</span>
      <input bind:value={label} maxlength="32" placeholder="e.g. Kitchen" />
    </label>

    <!-- Icon row: picker + show toggle + tint -->
    <div class="full">
      <div class="row-with-toggle">
        <span class="caption">Icon</span>
        <label class="checkbox inline">
          <input type="checkbox" bind:checked={showIcon} />
          <span>Show icon</span>
        </label>
      </div>
      <div class="icon-row">
        {#if iconId}
          <img class="preview" src={iconsApi.rawUrl(iconId)} alt="selected icon" />
          <code class="muted">{iconId}</code>
        {:else}
          <span class="muted">no icon selected</span>
        {/if}
        <button type="button" onclick={() => openPickerFor('icon')}>Choose…</button>
        {#if iconId}
          <button type="button" class="link" onclick={() => (iconId = null)}>Clear</button>
        {/if}
      </div>
      {#if showIcon}
        <label class="color-row">
          <input type="checkbox" bind:checked={iconTintEnabled} />
          <span>Tint icon</span>
          <input
            type="color"
            bind:value={iconColor}
            disabled={!iconTintEnabled}
            aria-label="Icon tint color"
          />
          <code class="muted small">{iconTintEnabled ? iconColor : '(none)'}</code>
        </label>
        <p class="muted small hint-line">
          Multiplies the icon's pixels by this color. Best on the bundled
          white icons; will recolor an already-colored uploaded icon.
        </p>
      {/if}
    </div>

    <!-- Label color (only shown when label is shown) -->
    <div class="full">
      <div class="row-with-toggle">
        <span class="caption">Label appearance</span>
        <label class="checkbox inline">
          <input type="checkbox" bind:checked={showLabel} />
          <span>Show label</span>
        </label>
      </div>
      {#if showLabel}
        <label class="color-row">
          <span>Color</span>
          <input
            type="color"
            bind:value={labelColor}
            aria-label="Label text color"
          />
          <code class="muted small">{labelColor}</code>
        </label>
        <label class="padding-row">
          <span>Font size</span>
          <input
            type="range"
            min="8"
            max="32"
            step="1"
            bind:value={fontSize}
            aria-label="Label font size in pixels"
          />
          <input
            type="number"
            min="8"
            max="32"
            step="1"
            bind:value={fontSize}
            class="padding-num"
          />
          <span class="muted small">px</span>
        </label>
        <p class="muted small hint-line">
          Lower values let longer labels fit. Padding doesn't shrink the
          font automatically — use this to compensate.
        </p>
      {/if}
    </div>

    <!-- Background color + image -->
    <div class="full">
      <span class="caption">Background</span>
      <label class="color-row">
        <span>Color</span>
        <input
          type="color"
          bind:value={bgColor}
          aria-label="Background color"
        />
        <code class="muted small">{bgColor}</code>
      </label>
      <div class="icon-row">
        {#if bgImageId}
          <img
            class="preview"
            src={iconsApi.rawUrl(bgImageId)}
            alt="selected background"
          />
          <code class="muted">{bgImageId}</code>
        {:else}
          <span class="muted">no background image</span>
        {/if}
        <button type="button" onclick={() => openPickerFor('bg')}>Choose…</button>
        {#if bgImageId}
          <button type="button" class="link" onclick={() => (bgImageId = null)}>
            Clear
          </button>
        {/if}
      </div>
      <p class="muted small hint-line">
        The background image is drawn over the color and under the icon,
        scaled to fill the key.
      </p>
    </div>

    <!-- Padding -->
    <div class="full">
      <label class="padding-row">
        <span>Padding</span>
        <input
          type="range"
          min="0"
          max="20"
          step="1"
          bind:value={padding}
          aria-label="Padding around key content (0 = no extra inset)"
        />
        <input
          type="number"
          min="0"
          max="20"
          step="1"
          bind:value={padding}
          class="padding-num"
        />
        <span class="muted small">px</span>
      </label>
      <p class="muted small hint-line">
        Extra inset around the icon and label. Increase if the icon feels
        cropped against the key edge.
      </p>
    </div>

    <div class="full">
      <span class="caption">Press action</span>
      <select
        value={press.type}
        onchange={(e) => setActionType((e.currentTarget as HTMLSelectElement).value as PressActionType)}
      >
        <option value="no_op">Do nothing</option>
        <option value="mqtt_publish">Publish MQTT message</option>
        <option value="http_webhook">Fire HTTP request</option>
        <option value="page_switch">Switch to another page</option>
      </select>

      {#if press.type === 'mqtt_publish'}
        <div class="sub">
          <label>
            <span>Topic</span>
            <input bind:value={press.topic} placeholder="home/kitchen/light/set" />
          </label>
          <label>
            <span>Payload</span>
            <input bind:value={press.payload} placeholder="ON / TOGGLE / JSON…" />
          </label>
          <label class="checkbox">
            <input type="checkbox" bind:checked={press.retain} />
            <span>Retain</span>
          </label>
          <label>
            <span>QoS</span>
            <select bind:value={press.qos}>
              <option value={0}>0</option>
              <option value={1}>1</option>
              <option value={2}>2</option>
            </select>
          </label>
        </div>
      {:else if press.type === 'http_webhook'}
        <div class="sub">
          <label>
            <span>URL</span>
            <input bind:value={press.url} placeholder="http://host:port/path" />
          </label>
          <label>
            <span>Method</span>
            <select bind:value={press.method}>
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
            </select>
          </label>
          <label>
            <span>Body (sent for POST/PUT)</span>
            <textarea bind:value={press.body} rows="3"></textarea>
          </label>
        </div>
      {:else if press.type === 'page_switch'}
        <div class="sub">
          <label>
            <span>Target page</span>
            <select bind:value={press.target_page_id}>
              <option value="" disabled>— pick a page —</option>
              {#each pages.filter((p) => p.id !== pageId) as p (p.id)}
                <option value={p.id}>{p.name || `(unnamed) ${p.id.slice(0, 8)}`}</option>
              {/each}
            </select>
          </label>
        </div>
      {/if}
    </div>

    <div class="full">
      <label class="checkbox">
        <input type="checkbox" bind:checked={stateEnabled} />
        <span>Subscribe to MQTT state and update the key icon based on incoming values</span>
      </label>

      {#if stateEnabled}
        <div class="sub">
          <label>
            <span>State topic</span>
            <input bind:value={stateSub.topic} placeholder="home/kitchen/light/state" />
          </label>
          <label>
            <span>JMESPath (optional, for JSON payloads)</span>
            <input bind:value={stateSub.jmespath} placeholder="state.power" />
          </label>

          <div class="caption row">
            <span>Value → icon</span>
            <button type="button" class="link" onclick={addMapRow}>+ Add row</button>
          </div>
          {#if mapRows.length === 0}
            <p class="muted small">No mappings — every value uses the default icon below.</p>
          {/if}
          {#each mapRows as row, i (i)}
            <div class="map-row">
              <input placeholder="value (e.g. on)" bind:value={row.value} />
              <input
                placeholder="icon id (e.g. lucide:lightbulb)"
                bind:value={row.iconId}
              />
              <button type="button" class="link danger" onclick={() => removeMapRow(i)}>
                Remove
              </button>
            </div>
          {/each}

          <label>
            <span>Default icon (used when no value matches)</span>
            <input
              bind:value={stateSub.default_icon_id}
              placeholder="lucide:circle-x"
            />
          </label>
        </div>
      {/if}
    </div>
  </div>

  {#if message}
    <p class="message">{message}</p>
  {/if}

  <div class="actions">
    <button
      type="button"
      class="primary"
      onclick={save}
      disabled={saving || deleting || testing}
    >
      {saving ? 'Saving…' : 'Save'}
    </button>
    <button
      type="button"
      onclick={testPress}
      disabled={saving || deleting || testing || !initial}
      title={initial ? 'Fire the configured action without a physical key press' : 'Save the key first to enable testing'}
    >
      {testing ? 'Testing…' : 'Test press'}
    </button>
    <button
      type="button"
      class="danger"
      onclick={clearKey}
      disabled={saving || deleting || testing}
    >
      {deleting ? 'Clearing…' : initial ? 'Clear slot' : 'Reset form'}
    </button>
  </div>
</div>

<IconPicker
  open={pickerOpen}
  selectedIconId={pickerTarget === 'icon' ? iconId : bgImageId}
  onSelect={(id) => {
    if (pickerTarget === 'icon') {
      iconId = id;
    } else {
      bgImageId = id;
    }
    pickerOpen = false;
  }}
  onClose={() => (pickerOpen = false)}
/>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    background: #fff;
    border-radius: 8px;
    padding: 1.25rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }
  h2 {
    margin: 0;
    font-size: 1.125rem;
  }
  .muted {
    color: #777;
    font-size: 0.875rem;
  }
  .small {
    font-size: 0.8125rem;
  }
  .grid {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  label.checkbox {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
  label span,
  .caption {
    font-size: 0.875rem;
    color: #444;
  }
  .full {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }
  input,
  select,
  textarea {
    padding: 0.4rem 0.625rem;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    font: inherit;
  }
  textarea {
    font-family: 'Inter', monospace;
    font-size: 0.875rem;
  }
  input:focus,
  select:focus,
  textarea:focus {
    outline: 2px solid #4c8bf5;
    outline-offset: -1px;
    border-color: #4c8bf5;
  }
  .icon-row {
    display: flex;
    align-items: center;
    gap: 0.625rem;
  }
  .preview {
    width: 32px;
    height: 32px;
    background: #1d1d1d;
    border-radius: 6px;
    padding: 4px;
    object-fit: contain;
  }
  .sub {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    background: #f7f7f7;
    border-radius: 6px;
    margin-top: 0.25rem;
  }
  .map-row {
    display: grid;
    grid-template-columns: 1fr 1.4fr auto;
    gap: 0.4rem;
    align-items: center;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.25rem;
  }
  .link {
    background: transparent;
    border: none;
    color: #4c8bf5;
    cursor: pointer;
    padding: 0.125rem 0.25rem;
    font-size: 0.875rem;
  }
  .link:hover {
    text-decoration: underline;
  }
  .link.danger {
    color: #b00020;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .primary {
    background: #1d1d1d;
    color: #fff;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
  }
  .primary:disabled {
    background: #888;
    cursor: not-allowed;
  }
  .danger {
    background: transparent;
    color: #b00020;
    border: 1px solid #d0d0d0;
    padding: 0.5rem 1rem;
    border-radius: 6px;
  }
  .danger:disabled {
    color: #888;
    cursor: not-allowed;
  }
  .row-with-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .checkbox.inline {
    flex-direction: row;
    align-items: center;
    gap: 0.375rem;
  }
  .color-row {
    flex-direction: row;
    align-items: center;
    gap: 0.625rem;
    margin-top: 0.375rem;
  }
  .color-row input[type='color'] {
    width: 2.5rem;
    height: 1.75rem;
    padding: 0;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    cursor: pointer;
  }
  .color-row input[type='color']:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
  .padding-row {
    flex-direction: row;
    align-items: center;
    gap: 0.625rem;
  }
  .padding-row > span:first-child {
    min-width: 5rem;
  }
  .padding-row input[type='range'] {
    flex: 1;
    padding: 0;
    border: none;
  }
  .padding-num {
    width: 3.5rem;
  }
  .hint-line {
    margin: 0.25rem 0 0;
  }
  .message {
    color: #444;
    margin: 0;
    font-size: 0.875rem;
  }
</style>
