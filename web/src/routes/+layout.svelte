<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  import { auth } from '$lib/stores/auth.svelte';

  import '../app.css';

  let { children } = $props();

  async function handleLogout() {
    await auth.logout();
    await goto('/login');
  }
</script>

{#if auth.state === 'authenticated'}
  <header class="topnav">
    <div class="brand"><span class="brand-mark"></span>DeckBridge</div>
    <nav>
      <a href="/editor" class:active={$page.url.pathname.startsWith('/editor')}>Editor</a>
      <a href="/diagnostics" class:active={$page.url.pathname.startsWith('/diagnostics')}
        >Diagnostics</a
      >
      <a href="/settings" class:active={$page.url.pathname.startsWith('/settings')}>Settings</a>
    </nav>
    <button type="button" class="logout" onclick={handleLogout}>Log out</button>
  </header>
{/if}

<main class="content">
  {@render children()}
</main>

<style>
  .topnav {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    padding: 0.7rem 1.5rem;
    background: var(--device-bg);
    color: #f1f1f1;
    position: sticky;
    top: 0;
    z-index: 50;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 650;
    letter-spacing: 0.01em;
  }
  .brand-mark {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: linear-gradient(135deg, var(--accent) 0%, #8a64ff 100%);
    box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
  }
  nav {
    display: flex;
    gap: 0.25rem;
    flex: 1;
  }
  nav a {
    color: #b6b9c2;
    text-decoration: none;
    padding: 0.35rem 0.7rem;
    border-radius: var(--r-sm);
    font-size: 0.92rem;
    font-weight: 500;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }
  nav a:hover {
    background: rgba(255, 255, 255, 0.06);
    color: #fff;
  }
  nav a.active {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }
  .logout {
    background: transparent;
    color: #b6b9c2;
    border: 1px solid rgba(255, 255, 255, 0.14);
    padding: 0.35rem 0.8rem;
    border-radius: var(--r-sm);
    font: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }
  .logout:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
  }
  .content {
    min-height: calc(100vh - 52px);
  }
</style>
