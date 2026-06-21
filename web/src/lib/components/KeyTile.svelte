<script lang="ts">
  import { icons as iconsApi } from '$lib/api/resources';
  import KeyPreview from './KeyPreview.svelte';

  import type { Key } from '$lib/api/types';

  interface Props {
    slot: number;
    keyConfig: Key | null;
    selected: boolean;
    onclick: (slot: number) => void;
  }

  let { slot, keyConfig, selected, onclick }: Props = $props();

  let iconUrl = $derived(keyConfig?.icon_id ? iconsApi.rawUrl(keyConfig.icon_id) : null);
  let bgImageUrl = $derived(
    keyConfig?.bg_image_id ? iconsApi.rawUrl(keyConfig.bg_image_id) : null,
  );
</script>

<button
  type="button"
  class="tile"
  class:selected
  class:empty={keyConfig === null}
  onclick={() => onclick(slot)}
  aria-label={`Key ${slot + 1}${keyConfig?.label ? `: ${keyConfig.label}` : ' (empty)'}`}
>
  {#if keyConfig}
    <KeyPreview
      label={keyConfig.label}
      {iconUrl}
      {bgImageUrl}
      showIcon={keyConfig.show_icon}
      showLabel={keyConfig.show_label}
      bgColor={keyConfig.bg_color}
      labelColor={keyConfig.label_color}
      iconColor={keyConfig.icon_color}
      fontSize={keyConfig.font_size}
      padding={keyConfig.padding}
    />
  {:else}
    <span class="plus" aria-hidden="true">+</span>
  {/if}
</button>

<style>
  .tile {
    width: 100%;
    aspect-ratio: 1;
    padding: 0;
    background: var(--device-key-empty);
    border: 2px solid transparent;
    border-radius: 11px;
    cursor: pointer;
    overflow: hidden;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    transition:
      border-color 0.12s ease,
      box-shadow 0.12s ease,
      transform 0.06s ease;
  }
  .tile:hover {
    border-color: var(--device-edge);
  }
  .tile.empty {
    border-style: dashed;
    border-color: #2b2d35;
  }
  .tile.empty:hover {
    border-color: #3c3f49;
  }
  .tile:active {
    transform: translateY(0.5px);
  }
  .tile.selected {
    border-color: var(--accent);
    border-style: solid;
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .tile:focus-visible {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-ring);
  }
  .plus {
    color: #3a3d47;
    font-size: 1.4rem;
    font-weight: 300;
    line-height: 1;
    transition: color 0.12s ease;
  }
  .tile.empty:hover .plus {
    color: #5a5e6b;
  }
</style>
