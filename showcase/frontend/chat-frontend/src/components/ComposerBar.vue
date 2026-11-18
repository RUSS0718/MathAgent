<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import UiButton from './ui/UiButton.vue'
import UiIcon from './ui/UiIcon.vue'
const props = defineProps<{
  modelValue: string
  disabled: boolean
  running: boolean
  visionEnabled: boolean
  hasImage?: boolean
  uploading?: boolean
  selectedFileName?: string
  waiting?: boolean
  submitLabel?: string
  submitDisabled?: boolean
  commandEnabled?: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
  cancel: []
  upload: [event: Event]
  clearFile: []
}>()

const fileInput = ref<HTMLInputElement>()
const input = ref<HTMLTextAreaElement>()
const commands = [['solve', '求解'], ['teach', '教学'], ['report', '报告']] as const
const selected = computed(() => /^\/(solve|teach|report)\s/.exec(props.modelValue)?.[1])
const text = computed(() => selected.value ? props.modelValue.replace(/^\/(solve|teach|report)\s+/, '') : props.modelValue)
const canSubmit = computed(() => !props.disabled && !props.submitDisabled && !props.uploading &&
  (props.hasImage || props.modelValue.trim()))
function submit() { if (canSubmit.value) emit('submit') }
const dismissed = ref(false)
const active = ref(0)
const candidates = computed(() => props.commandEnabled && !selected.value && !dismissed.value && /^\/[a-z]*$/.test(text.value) ? commands.filter(item => item[0].startsWith(text.value.slice(1))) : [])
const selectedLabel = computed(() => commands.find(item => item[0] === selected.value)?.[1])
function update(value: string) { dismissed.value = false; active.value = 0; emit('update:modelValue', selected.value ? `/${selected.value} ${value}` : value) }
function choose(mode: string) { emit('update:modelValue', `/${mode} `); void nextTick(() => input.value?.focus()) }
function removeCommand() { emit('update:modelValue', text.value); void nextTick(() => input.value?.focus()) }
function handleKeydown(event: KeyboardEvent): void {
  if (event.isComposing || event.keyCode === 229) return
  if (candidates.value.length) {
    if (event.key === 'Escape') { event.preventDefault(); dismissed.value = true; return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); active.value = (active.value + (event.key === 'ArrowDown' ? 1 : candidates.value.length - 1)) % candidates.value.length; return }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); choose(candidates.value[active.value]![0]); return }
  }
  if (event.key === 'Backspace' && !text.value && selected.value) { event.preventDefault(); removeCommand(); return }
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() }
}
</script>

<template>
  <form class="composer-shell" @submit.prevent="submit">
    <slot name="mode"></slot>
    <div v-if="selectedFileName" class="file-chip"><UiIcon name="image" />{{ selectedFileName }}<UiButton icon-only variant="ghost" :disabled="disabled || uploading" aria-label="移除题图" @click="emit('clearFile')"><UiIcon name="close" /></UiButton></div>
    <label class="sr-only" for="math-question">数学问题</label>
    <div v-if="selected" class="command-chip"><span>/{{ selected }} · {{ selectedLabel }}</span><UiButton icon-only variant="ghost" :disabled="disabled" :aria-label="`移除${selectedLabel}规则`" @click="removeCommand"><UiIcon name="close" /></UiButton></div>
    <div v-if="candidates.length" id="answer-commands" role="listbox" aria-label="答复规则" class="command-options"><div v-for="(item, index) in candidates" :id="`answer-command-${item[0]}`" :key="item[0]" role="option" :aria-selected="index === active" @mousedown.prevent="choose(item[0])">/{{ item[0] }} · {{ item[1] }}</div></div>
    <textarea ref="input" id="math-question" :value="text" :aria-controls="candidates.length ? 'answer-commands' : undefined" :aria-expanded="candidates.length ? true : undefined" :aria-activedescendant="candidates[active] ? `answer-command-${candidates[active]![0]}` : undefined" :disabled="disabled" :placeholder="waiting ? '补充题目条件，继续当前运行' : '输入数学问题'" @input="update(($event.target as HTMLTextAreaElement).value)" @keydown="handleKeydown"></textarea>
    <div class="composer-footer">
      <div class="composer-tools"><template v-if="visionEnabled"><input ref="fileInput" hidden type="file" accept="image/png" aria-label="选择 PNG 题图" @change="emit('upload', $event)" /><UiButton variant="ghost" :disabled="disabled || running || uploading" @click="fileInput?.click()"><UiIcon name="image" />{{ uploading ? '正在上传…' : '题图' }}</UiButton></template></div>
      <div class="composer-actions"><UiButton v-if="running" variant="danger" @click="emit('cancel')"><UiIcon name="stop" />停止</UiButton><UiButton v-if="!running || waiting" variant="primary" type="submit" :busy="busy" :disabled="!canSubmit">{{ submitLabel ?? (waiting ? '补充条件' : '发送') }}<UiIcon name="arrowUp" /></UiButton></div>
    </div>
  </form>
</template>

<style scoped>
.command-chip { display:flex; align-items:center; gap:8px; width:fit-content; margin:12px 16px 0; padding-left:12px; border-radius:var(--radius-md); background:var(--accent-wash); color:var(--accent-strong); }
.command-options { margin:12px 16px 0; border:1px solid var(--border); border-radius:var(--radius-md); }
.command-options [role=option] { padding:10px 12px; cursor:pointer; }
.command-options [aria-selected=true] { background:var(--accent-wash); color:var(--accent-strong); }
</style>
