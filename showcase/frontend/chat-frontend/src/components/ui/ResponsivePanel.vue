<script setup lang="ts">
/** Native modal focus/inert behavior on narrow screens; in-flow panel on desktop. */
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
const props = defineProps<{ open: boolean; label: string; breakpoint: number; side: 'left' | 'right'; id: string; persistent?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const narrow = ref(globalThis.matchMedia(`(max-width: ${props.breakpoint}px)`).matches)
const dialog = ref<HTMLDialogElement>()
const media = globalThis.matchMedia(`(max-width: ${props.breakpoint}px)`)
function onResize(): void { narrow.value = media.matches }
async function syncDialog(): Promise<void> {
  await nextTick()
  if (narrow.value && props.open && !dialog.value?.open) dialog.value?.showModal()
  else if (dialog.value?.open && !props.open) dialog.value.close()
}
function closeFromBackdrop(event: MouseEvent): void {
  if (event.target !== dialog.value) return
  const bounds = dialog.value.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) emit('close')
}
watch([() => props.open, narrow], syncDialog)
onMounted(() => { media.addEventListener('change', onResize); void syncDialog() })
onUnmounted(() => media.removeEventListener('change', onResize))
</script>

<template>
  <dialog v-if="narrow" :id="id" ref="dialog" class="panel-dialog" :class="`panel-dialog--${side}`" :aria-label="label" @cancel.prevent="emit('close')" @click="closeFromBackdrop"><slot /></dialog>
  <div v-else v-show="persistent || open" :id="id" class="panel-inline"><slot /></div>
</template>
