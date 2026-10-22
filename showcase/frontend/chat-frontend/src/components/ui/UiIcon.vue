<script setup lang="ts">
/** Import only this finite icon set; never load the whole library dynamically. */
import { Activity, ArrowDownToLine, ArrowRight, ArrowUp, Check, ChevronDown, ChevronRight, FlaskConical, Menu, MessageSquare, PanelRight, Pencil, Plus, RefreshCw, Settings, Sigma, Square, Trash2, X, Image } from '@lucide/vue'
const icons = { activity: Activity, download: ArrowDownToLine, arrowRight: ArrowRight, arrowUp: ArrowUp, check: Check, chevronDown: ChevronDown, chevronRight: ChevronRight, experiments: FlaskConical, menu: Menu, message: MessageSquare, panel: PanelRight, pencil: Pencil, plus: Plus, refresh: RefreshCw, settings: Settings, sigma: Sigma, stop: Square, trash: Trash2, close: X, image: Image }
defineProps<{ name: keyof typeof icons }>()
</script>

<template><component :is="icons[name]" class="ui-icon" :size="18" :stroke-width="1.75" aria-hidden="true" focusable="false" /></template>
