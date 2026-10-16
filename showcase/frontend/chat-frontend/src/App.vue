<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from './stores/auth.store'
import { useSessionsStore } from './stores/sessions.store'
import { readDashboardRoute, type DashboardRoute } from './runtime/navigation/app-route'
import ChatWorkspace from './components/ChatWorkspace.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const auth = useAuthStore()
const sessions = useSessionsStore()
const route = ref<DashboardRoute>(readDashboardRoute(globalThis.location.pathname))
const ready = ref(false)
onMounted(async () => { await auth.check(); await sessions.loadList(); ready.value = true; globalThis.addEventListener('popstate', () => { route.value = readDashboardRoute(globalThis.location.pathname) }) })
</script>
<template><p v-if="!ready" class="loading">加载中...</p><SettingsPanel v-else-if="route.view === 'settings'" /><ChatWorkspace v-else :path="route.path" /></template>
