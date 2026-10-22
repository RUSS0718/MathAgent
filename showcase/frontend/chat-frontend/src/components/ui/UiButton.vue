<script setup lang="ts">
/** Native button semantics, with one shared visual vocabulary. */
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  iconOnly?: boolean
  busy?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), { variant: 'secondary', type: 'button' })
</script>

<template>
  <button :type="type" class="ui-button" :class="[`ui-button--${variant}`, { 'ui-button--icon': iconOnly }]" :disabled="disabled || busy" :aria-busy="busy || undefined">
    <slot />
  </button>
</template>
