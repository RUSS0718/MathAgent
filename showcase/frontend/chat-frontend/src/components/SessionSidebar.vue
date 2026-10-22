<script setup lang="ts">
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
import ResponsivePanel from './ui/ResponsivePanel.vue'
defineProps<{
  items: Array<{ id: string; preview: string; lastTime: string }>
  currentId: string | null
  open: boolean
}>()

const emit = defineEmits<{
  new: []
  select: [id: string]
  rename: [id: string]
  remove: [id: string]
  settings: []
  close: []
}>()
</script>

<template>
  <ResponsivePanel id="session-panel" :open="open" :breakpoint="760" side="left" label="会话导航" persistent @close="emit('close')">
  <aside class="session-sidebar" aria-label="会话导航">
    <div class="brand-block">
      <div class="brand-mark"><UiIcon name="sigma" /></div>
      <div><strong>MathAgent</strong><small>数学推理工作区</small></div>
      <UiButton icon-only variant="ghost" class="mobile-only" aria-label="关闭会话栏" @click="emit('close')"><UiIcon name="close" /></UiButton>
    </div>
    <nav class="sidebar-nav" aria-label="主导航"><UiButton variant="primary" @click="emit('new')"><UiIcon name="plus" />新建会话</UiButton><a class="ui-button ui-button--ghost" href="/dashboard/campaigns"><UiIcon name="experiments" />配对实验</a></nav>
    <div class="sidebar-section"><div class="sidebar-section-label"><span>最近会话</span><span>{{ items.length }}</span></div>
    <div v-if="!items.length" class="sidebar-empty">还没有数学题记录</div>
    <nav v-else class="session-list" aria-label="数学会话">
      <div v-for="item in items" :key="item.id" class="session-row" :class="{ selected: item.id === currentId }">
        <button class="session-main" type="button" :aria-current="item.id === currentId ? 'page' : undefined" @click="emit('select', item.id)">
          <span class="session-title">{{ item.preview }}</span><span class="session-time">{{ item.lastTime }}</span>
        </button>
        <div class="session-actions">
          <UiButton icon-only variant="ghost" :aria-label="`重命名会话：${item.preview}`" @click="emit('rename', item.id)"><UiIcon name="pencil" /></UiButton>
          <UiButton icon-only variant="ghost" :aria-label="`删除会话：${item.preview}`" @click="emit('remove', item.id)"><UiIcon name="trash" /></UiButton>
        </div>
      </div>
    </nav>
    </div>
    <div class="sidebar-footer"><UiButton variant="ghost" @click="emit('settings')"><UiIcon name="settings" />设置</UiButton><span class="profile-label">本机用户</span></div>
  </aside>
  </ResponsivePanel>
</template>
