<script setup lang="ts">
defineProps<{
  modelValue: string
  disabled: boolean
  running: boolean
  visionEnabled: boolean
  selectedFileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
  cancel: []
  upload: [event: Event]
  clearFile: []
}>()

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    emit('submit')
  }
}
</script>

<template>
  <form class="composer-shell" @submit.prevent="running ? emit('cancel') : emit('submit')">
    <div v-if="selectedFileName" class="file-chip"><span aria-hidden="true">▧</span>{{ selectedFileName }}<button type="button" aria-label="移除题图" @click="emit('clearFile')">×</button></div>
    <textarea :value="modelValue" :disabled="disabled" aria-label="数学问题" placeholder="输入数学问题，Shift + Enter 换行" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" @keydown="handleKeydown"></textarea>
    <div class="composer-footer"><div class="composer-tools"><label v-if="visionEnabled" class="tool-button" title="上传 PNG 题图"><span aria-hidden="true">＋</span><input type="file" accept="image/png" @change="emit('upload', $event)" />图片</label><span class="composer-hint">公开报告会保留验证边界</span></div><div class="composer-actions"><span class="keyboard-hint">Enter 发送</span><button v-if="running" class="send-button cancel" type="button" @click="emit('cancel')">停止</button><button v-else class="send-button" type="submit" :disabled="disabled || !modelValue.trim()">发送 <span aria-hidden="true">↑</span></button></div></div>
  </form>
</template>
