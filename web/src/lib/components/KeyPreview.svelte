<script lang="ts">
  /**
   * Pixel-faithful preview of how a key will look on the physical deck.
   *
   * Mirrors `src/deckbridge/device/renderer.py`: the device renders each key
   * in a 72x72 space with icon margins of `6+padding` (x), `4+padding` (top)
   * and `18+padding` (bottom, when a label is present), the label bottom-
   * anchored 4px from the edge, and the icon tint applied as an RGB multiply
   * (which for the bundled white icons is exactly the tint color — modelled
   * here with a CSS mask fill).
   *
   * Everything is expressed in device units (1u = one 72px-key pixel) via the
   * `--u` custom property, which resolves to a fraction of the container using
   * container-query units. That keeps the preview true-to-device whether it's
   * rendered tiny in the deck grid or large in the editor — the parent just
   * sets the box size (or pass `size` for a self-sized standalone preview).
   */

  interface Props {
    label: string;
    iconUrl: string | null;
    showIcon?: boolean;
    showLabel?: boolean;
    bgColor?: string;
    bgImageUrl?: string | null;
    labelColor?: string;
    iconColor?: string | null;
    fontSize?: number;
    padding?: number;
    /** Optional fixed size in px. Omit to fill the parent element. */
    size?: number | null;
  }

  let {
    label,
    iconUrl,
    showIcon = true,
    showLabel = true,
    bgColor = '#000000',
    bgImageUrl = null,
    labelColor = '#FFFFFF',
    iconColor = null,
    fontSize = 14,
    padding = 0,
    size = null,
  }: Props = $props();

  let hasIcon = $derived(showIcon && !!iconUrl);
  let hasLabel = $derived(showLabel && label.trim().length > 0);

  // Icon content box (device units), matching renderer._paste_icon margins.
  let marginX = $derived(6 + padding);
  let marginTop = $derived(4 + padding);
  let marginBottom = $derived((hasLabel ? 18 : 4) + padding);
</script>

<div
  class="key"
  style={size != null ? `width:${size}px;height:${size}px` : ''}
>
  <div
    class="surface"
    style="
      background-color: {bgColor};
      {bgImageUrl ? `background-image: url('${bgImageUrl}');` : ''}
    "
  >
    {#if hasIcon}
      <div
        class="icon-box"
        style="
          left: calc({marginX} * var(--u));
          top: calc({marginTop} * var(--u));
          right: calc({marginX} * var(--u));
          bottom: calc({marginBottom} * var(--u));
        "
      >
        {#if iconColor}
          <span
            class="icon tinted"
            style="background-color: {iconColor}; -webkit-mask-image: url('{iconUrl}'); mask-image: url('{iconUrl}');"
          ></span>
        {:else}
          <img class="icon" src={iconUrl} alt="" draggable="false" />
        {/if}
      </div>
    {/if}

    {#if hasLabel}
      <div
        class="label"
        class:centered={!hasIcon}
        style="
          color: {labelColor};
          font-size: calc({fontSize} * var(--u));
          bottom: calc({4 + padding} * var(--u));
        "
      >
        {label}
      </div>
    {/if}
  </div>
</div>

<style>
  .key {
    flex: none;
    width: 100%;
    height: 100%;
    aspect-ratio: 1;
    container-type: size;
  }
  .surface {
    position: relative;
    width: 100%;
    height: 100%;
    /* 1 device unit = 1/72 of the smaller container side. */
    --u: calc(100cqmin / 72);
    border-radius: calc(9 * var(--u));
    overflow: hidden;
    background-position: center;
    background-size: cover;
    background-repeat: no-repeat;
  }
  .icon-box {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .icon {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .icon.tinted {
    width: 100%;
    height: 100%;
    -webkit-mask-position: center;
    mask-position: center;
    -webkit-mask-repeat: no-repeat;
    mask-repeat: no-repeat;
    -webkit-mask-size: contain;
    mask-size: contain;
  }
  .label {
    position: absolute;
    left: 0;
    right: 0;
    padding: 0 2px;
    text-align: center;
    line-height: 1.05;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: clip;
  }
  .label.centered {
    top: 0;
    bottom: 0 !important;
    display: flex;
    align-items: center;
    justify-content: center;
  }
</style>
