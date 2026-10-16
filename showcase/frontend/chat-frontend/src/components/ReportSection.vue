<script setup lang="ts">
import { computed } from 'vue'
import { renderSafeMarkdown } from '../renderers/markdown-adapter'
const props = defineProps<{ title: string; content: string }>()
const html = computed(() => renderSafeMarkdown(props.content))
</script>
<template><section class="report-section"><h2>{{ title }}</h2><div v-html="html"></div></section></template>
