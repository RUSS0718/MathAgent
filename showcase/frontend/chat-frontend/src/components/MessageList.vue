<script setup lang="ts">
import type { ChatMessageResponse } from '../api/sessions.schemas'
import UiIcon from './ui/UiIcon.vue'

defineProps<{ messages: ChatMessageResponse[] }>()
const emit = defineEmits<{ starter: [value: string] }>()
const starters = [
  { title: '解方程并说明验证过程', example: 'x² − 5x + 6 = 0', prompt: '解方程 x² − 5x + 6 = 0，并说明验证过程。' },
  { title: '分析一个多项式的候选根', example: '验证 1、−1 是否为 x³ − x 的根', prompt: '验证 1、−1 是否为多项式 x³ − x 的根，并说明检查范围。' },
  { title: '给出一道题的分步推导', example: '求 1 + 2 + … + n 的和', prompt: '分步推导 1 + 2 + … + n 的求和公式，n 为正整数。' },
]
</script>

<template>
  <div class="message-list" aria-live="polite">
    <section v-if="!messages.length" class="welcome-panel">
      <h2>把复杂数学题，<br>拆成可验证的步骤。</h2>
      <p class="welcome-copy">输入一道数学题，观察规划、求解、工具和验证节点如何协同完成答案。</p>
      <div class="starter-list"><button v-for="starter in starters" :key="starter.title" type="button" @click="emit('starter', starter.prompt)"><span>{{ starter.title }}<small>{{ starter.example }}</small></span><UiIcon name="arrowRight" /></button></div>
    </section>
    <template v-else>
      <article v-for="(message, index) in messages" :key="`${message.analysis_job_id}-${index}`" class="message-card" :class="message.sender">
        <div class="message-avatar" :class="message.sender" aria-hidden="true"><UiIcon name="sigma" /></div>
        <div class="message-body"><div class="message-label">{{ message.sender === 'user' ? '你的问题' : 'MathAgent' }}</div><p>{{ message.text }}</p></div>
      </article>
    </template>
  </div>
</template>
