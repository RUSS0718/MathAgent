<script setup lang="ts">
/** Shared navigation and reading width for settings and public evidence screens. */
import UiIcon from './UiIcon.vue'
defineProps<{ title: string; description?: string; active: 'settings' | 'campaigns' | 'run' }>()
</script>

<template>
  <div class="page-frame">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="app-header">
      <a class="brand-block" href="/dashboard"><span class="brand-mark"><UiIcon name="sigma" /></span><strong>MathAgent</strong></a>
      <nav class="app-nav" aria-label="主导航">
        <a href="/dashboard"><UiIcon name="message" />数学工作区</a>
        <a href="/dashboard/campaigns" :aria-current="active === 'campaigns' || active === 'run' ? 'page' : undefined"><UiIcon name="experiments" />配对实验</a>
        <a href="/dashboard/settings" :aria-current="active === 'settings' ? 'page' : undefined"><UiIcon name="settings" />设置</a>
      </nav>
    </header>
    <main id="main-content" class="page-content" tabindex="-1">
      <header class="page-heading"><div><h1>{{ title }}</h1><p v-if="description" class="page-description">{{ description }}</p></div><div v-if="$slots.actions" class="action-row"><slot name="actions" /></div></header>
      <slot />
    </main>
    <footer class="page-footer">MathAgent · 本机 Showcase 工作区</footer>
  </div>
</template>
