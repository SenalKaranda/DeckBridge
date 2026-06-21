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
    gap: 0.6rem;
    width: 100%;
    max-width: 30rem;
    background:
      radial-gradient(120% 120% at 50% 0%, #16171c 0%, var(--device-bg) 70%);
    padding: 0.9rem;
    border-radius: var(--r-xl);
    border: 1px solid #000;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.04),
      var(--shadow-md);
  }
</style>
