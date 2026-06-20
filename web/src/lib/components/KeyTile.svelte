<script lang="ts">
  import { icons as iconsApi } from '$lib/api/resources';

  import type { Key } from '$lib/api/types';

  interface Props {
    slot: number;
    keyConfig: Key | null;
    selected: boolean;
    onclick: (slot: number) => void;
  }

  let { slot, keyConfig, selected, onclick }: Props = $props();

  let label = $derived(keyConfig?.label ?? '');
  let iconUrl = $derived(keyConfig?.icon_id ? iconsApi.rawUrl(keyConfig.icon_id) : null);
</script>

<button
  type="button"
  class="tile"
  class:selected
  class:configured={keyConfig !== null}
  onclick={() => onclick(slot)}
  aria-label={`Key slot ${slot}${label ? `: ${label}` : ''}`}
>
  {#if iconUrl}
    <img src={iconUrl} alt="" class="icon" loading="lazy" />
  {/if}
  {#if label}
    <span class="label">{label}</span>
  {:else if !keyConfig}
    <span class="slot-num">{slot}</span>
  {/if}
</button>

<style>
  .tile {
    width: 100%;
    aspect-ratio: 1;
    background: #161616;
    border: 2px solid transparent;
    border-radius: 10px;
    color: #888;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    padding: 0.5rem;
    cursor: pointer;
    transition: border-color 100ms ease, background 100ms ease;
    overflow: hidden;
    position: relative;
  }
  .tile:hover {
    border-color: #444;
  }
  .tile.configured {
    background: #1d1d1d;
    color: #f1f1f1;
  }
  .tile.selected {
    border-color: #4c8bf5;
    background: #232f47;
  }
  .icon {
    width: 60%;
    height: 60%;
    object-fit: contain;
    image-rendering: -webkit-optimize-contrast;
  }
  .label {
    font-size: 0.75rem;
    line-height: 1.1;
    text-align: center;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .slot-num {
    font-size: 0.75rem;
    color: #555;
    font-variant-numeric: tabular-nums;
  }
</style>
