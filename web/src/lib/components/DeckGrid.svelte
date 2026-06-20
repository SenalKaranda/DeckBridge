<script lang="ts">
  import KeyTile from './KeyTile.svelte';

  import type { Key } from '$lib/api/types';

  interface Props {
    keys: Key[];
    selectedSlot: number | null;
    onSlotClick: (slot: number) => void;
    rows?: number;
    cols?: number;
  }

  let { keys, selectedSlot, onSlotClick, rows = 3, cols = 5 }: Props = $props();

  let total = $derived(rows * cols);

  let bySlot = $derived(
    new Map(keys.map((k) => [k.slot, k] as const)),
  );
</script>

<div
  class="grid"
  style="grid-template-columns: repeat({cols}, 1fr); grid-template-rows: repeat({rows}, 1fr);"
>
  {#each Array.from({ length: total }, (_, i) => i) as slot (slot)}
    <KeyTile
      {slot}
      keyConfig={bySlot.get(slot) ?? null}
      selected={selectedSlot === slot}
      onclick={onSlotClick}
    />
  {/each}
</div>

<style>
  .grid {
    display: grid;
    gap: 0.625rem;
    width: 100%;
    max-width: 30rem;
    background: #0a0a0a;
    padding: 0.75rem;
    border-radius: 14px;
    border: 1px solid #222;
  }
</style>
