<script setup lang="ts">
import { ref } from 'vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
defineProps<{
  modelValue: string
  disabled: boolean
  running: boolean
  visionEnabled: boolean
  selectedFileName?: string
  waiting?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
  cancel: []
  upload: [event: Event]
  clearFile: []
}>()

const fileInput = ref<HTMLInputElement>()
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    emit('submit')
  }
}
</script>

<template>
  <form class="composer-shell" @submit.prevent="emit('submit')">
    <slot name="mode"></slot>
    <div v-if="selectedFileName" class="file-chip"><UiIcon name="image" />{{ selectedFileName }}<UiButton icon-only variant="ghost" aria-label="移除题图" @click="emit('clearFile')"><UiIcon name="close" /></UiButton></div>
    <label class="sr-only" for="math-question">数学问题</label>
    <textarea id="math-question" :value="modelValue" :disabled="disabled" :placeholder="waiting ? '补充题目条件，继续当前运行' : '输入数学问题，Shift + Enter 换行'" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" @keydown="handleKeydown"></textarea>
    <div class="composer-footer">
      <div class="composer-tools"><template v-if="visionEnabled"><input ref="fileInput" hidden type="file" accept="image/png" @change="emit('upload', $event)" /><UiButton variant="ghost" :disabled="disabled || running" @click="fileInput?.click()"><UiIcon name="image" />题图</UiButton></template><span class="composer-hint">公开报告会保留验证边界</span></div>
      <div class="composer-actions"><span class="keyboard-hint">Enter 发送</span><UiButton v-if="running" variant="danger" @click="emit('cancel')"><UiIcon name="stop" />停止</UiButton><UiButton v-if="!running || waiting" variant="primary" type="submit" :disabled="disabled || !modelValue.trim()">{{ waiting ? '补充条件' : '发送' }}<UiIcon name="arrowUp" /></UiButton></div>
    </div>
  </form>
</template>
