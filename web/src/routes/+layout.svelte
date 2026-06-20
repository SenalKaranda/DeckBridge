<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  import { auth } from '$lib/stores/auth.svelte';

  let { children } = $props();

  async function handleLogout() {
    await auth.logout();
    await goto('/login');
  }
</script>

{#if auth.state === 'authenticated'}
  <header class="topnav">
    <div class="brand">DeckBridge</div>
    <nav>
      <a href="/editor" class:active={$page.url.pathname.startsWith('/editor')}>Editor</a>
      <a href="/diagnostics" class:active={$page.url.pathname.startsWith('/diagnostics')}
        >Diagnostics</a
      >
      <a href="/settings" class:active={$page.url.pathname.startsWith('/settings')}>Settings</a>
    </nav>
    <button type="button" onclick={handleLogout}>Log out</button>
  </header>
{/if}

<main class="content">
  {@render children()}
</main>

<style>
  :global(html),
  :global(body) {
    margin: 0;
    padding: 0;
    background: #fafafa;
    color: #111;
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.5;
  }
  :global(h1, h2, h3) {
    font-weight: 600;
    margin: 0 0 0.5rem 0;
  }
  :global(button) {
    font: inherit;
    cursor: pointer;
  }

  .topnav {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1.5rem;
    background: #1d1d1d;
    color: #f1f1f1;
    border-bottom: 1px solid #000;
  }
  .brand {
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  nav {
    display: flex;
    gap: 0.75rem;
    flex: 1;
  }
  nav a {
    color: #c8c8c8;
    text-decoration: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }
  nav a:hover {
    background: #2a2a2a;
    color: #fff;
  }
  nav a.active {
    background: #333;
    color: #fff;
  }
  .topnav button {
    background: transparent;
    color: #c8c8c8;
    border: 1px solid #444;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
  }
  .topnav button:hover {
    background: #2a2a2a;
    color: #fff;
  }

  .content {
    min-height: calc(100vh - 56px);
  }
</style>
