<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from './stores/auth.store'
import { useSessionsStore } from './stores/sessions.store'
import { readDashboardRoute, type DashboardRoute } from './runtime/navigation/app-route'
import ChatWorkspace from './components/ChatWorkspace.vue'
import CampaignWorkbench from './components/CampaignWorkbench.vue'
import RunReview from './components/RunReview.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import FaithfulSystemView from './components/FaithfulSystemView.vue'
import UiButton from './components/ui/UiButton.vue'
import UiIcon from './components/ui/UiIcon.vue'

const auth = useAuthStore()
const sessions = useSessionsStore()
const route = ref<DashboardRoute>(readDashboardRoute(globalThis.location.pathname))
const ready = ref(false)
const restricted = computed(() => route.value.view === 'reviewer' || (route.value.view !== 'workspace' && !auth.reviewer))
const reviewerSecret = ref('')
const grantError = ref('')
async function grant() { try { await (await import('./api/client')).api.grantReviewer(reviewerSecret.value); reviewerSecret.value = ''; await auth.check(); globalThis.location.assign('/dashboard/settings') } catch { reviewerSecret.value = ''; grantError.value = '无法取得审阅权限，请检查授权信息。' } }
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
  <main v-if="!ready" class="startup-state"><div class="brand-block"><span class="brand-mark"><UiIcon name="sigma" /></span><h1>因果推理智能体</h1></div><template v-if="error"><p class="notice notice--error" role="alert">{{ error }}</p><UiButton variant="primary" @click="initialize">重新连接</UiButton></template><div v-else role="status" aria-busy="true"><p>正在连接本机工作区…</p><div v-for="n in 3" :key="n" class="skeleton"></div></div></main>
  <main v-else-if="restricted" class="startup-state"><h1>技术审阅需要授权</h1><form @submit.prevent="grant"><label for="reviewer-secret">审阅密钥</label><input id="reviewer-secret" v-model="reviewerSecret" type="password" autocomplete="off" required /><UiButton type="submit">授权审阅</UiButton></form><p v-if="grantError" role="alert">{{ grantError }}</p><a href="/dashboard">返回数学工作区</a></main>
  <CampaignWorkbench v-else-if="route.view === 'campaigns'" />
  <RunReview v-else-if="route.view === 'run'" :key="route.runId" :job-id="route.runId!" />
  <FaithfulSystemView v-else-if="route.view === 'system'" />
  <SettingsPanel v-else-if="route.view === 'settings'" />
  <ChatWorkspace v-else :key="route.path" :path="route.path" :session-id="route.sessionId" />
</template>
