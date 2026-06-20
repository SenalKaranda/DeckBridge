<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  // Index route: the layout has already classified the auth state and
  // bounced us to /setup or /login if appropriate. If we landed here as an
  // authenticated user, send them straight to the editor.
  onMount(() => {
    void goto('/editor', { replaceState: true });
  });
</script>

<p style="padding: 2rem;">Loading…</p>
