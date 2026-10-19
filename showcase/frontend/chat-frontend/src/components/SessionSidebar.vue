<script setup lang="ts">
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
  <aside class="session-sidebar" :class="{ 'is-open': open }">
    <div class="brand-block">
      <div class="brand-mark" aria-hidden="true">∑</div>
      <div><strong>MathAgent</strong><span>数学推理工作区</span></div>
      <button class="icon-button mobile-only" type="button" aria-label="关闭会话栏" @click="emit('close')">×</button>
    </div>
    <button class="new-session-button" type="button" @click="emit('new')"><span aria-hidden="true">＋</span> 新建会话</button>
    <div class="sidebar-section-label"><span>最近会话</span><span>{{ items.length }}</span></div>
    <div v-if="!items.length" class="sidebar-empty">还没有数学题记录</div>
    <nav v-else class="session-list" aria-label="数学会话">
      <div v-for="item in items" :key="item.id" class="session-row" :class="{ selected: item.id === currentId }">
        <button class="session-main" type="button" @click="emit('select', item.id)">
          <span class="session-title">{{ item.preview }}</span><span class="session-time">{{ item.lastTime }}</span>
        </button>
        <div class="session-actions">
          <button type="button" aria-label="重命名会话" @click="emit('rename', item.id)">···</button>
          <button type="button" aria-label="删除会话" @click="emit('remove', item.id)">×</button>
        </div>
      </div>
    </nav>
    <div class="sidebar-footer"><button type="button" class="settings-link" @click="emit('settings')"><span aria-hidden="true">⚙</span> 设置</button><span class="profile-dot" aria-hidden="true"></span><span class="profile-label">本机用户</span></div>
  </aside>
</template>
