<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from './stores/auth.store'
import { useSessionsStore } from './stores/sessions.store'
import { readDashboardRoute, type DashboardRoute } from './runtime/navigation/app-route'
import ChatWorkspace from './components/ChatWorkspace.vue'
import CampaignWorkbench from './components/CampaignWorkbench.vue'
import RunReview from './components/RunReview.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import UiButton from './components/ui/UiButton.vue'
import UiIcon from './components/ui/UiIcon.vue'

const auth = useAuthStore()
const sessions = useSessionsStore()
const route = ref<DashboardRoute>(readDashboardRoute(globalThis.location.pathname))
const ready = ref(false)
const error = ref('')
async function initialize(): Promise<void> {
  error.value = ''
  try { if (!await auth.check()) throw new Error('本机身份尚未就绪，请重试。'); await sessions.loadList(); ready.value = true }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '工作区加载失败。' }
}
function navigate(): void { route.value = readDashboardRoute(globalThis.location.pathname) }
onMounted(() => { void initialize(); globalThis.addEventListener('popstate', navigate) })
onUnmounted(() => globalThis.removeEventListener('popstate', navigate))
</script>
<template>
  <main v-if="!ready" class="startup-state"><div class="brand-block"><span class="brand-mark"><UiIcon name="sigma" /></span><h1>MathAgent</h1></div><template v-if="error"><p class="notice notice--error" role="alert">{{ error }}</p><UiButton variant="primary" @click="initialize">重新连接</UiButton></template><div v-else role="status" aria-busy="true"><p>正在连接本机工作区…</p><div v-for="n in 3" :key="n" class="skeleton"></div></div></main>
  <CampaignWorkbench v-else-if="route.view === 'campaigns'" />
  <RunReview v-else-if="route.view === 'run'" :key="route.runId" :job-id="route.runId!" />
  <SettingsPanel v-else-if="route.view === 'settings'" />
  <ChatWorkspace v-else :key="route.path" :path="route.path" :session-id="route.sessionId" />
</template>
