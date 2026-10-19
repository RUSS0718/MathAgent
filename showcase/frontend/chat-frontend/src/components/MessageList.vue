<script setup lang="ts">
import type { ChatMessageResponse } from '../api/sessions.schemas'

defineProps<{ messages: ChatMessageResponse[] }>()
const emit = defineEmits<{ starter: [value: string] }>()
const starters = ['解方程并说明验证过程', '分析一个多项式的候选根', '给出一道题的分步推导']
</script>

<template>
  <div class="message-list" aria-live="polite">
    <section v-if="!messages.length" class="welcome-panel">
      <div class="welcome-orbit" aria-hidden="true"><span>∑</span></div>
      <p class="eyebrow">MATHAGENT WORKSPACE</p>
      <h1>把复杂数学题，<br><em>拆成可验证的步骤。</em></h1>
      <p class="welcome-copy">输入一道数学题，观察规划、求解、工具和验证节点如何协同完成答案。</p>
      <div class="starter-grid"><button v-for="starter in starters" :key="starter" type="button" @click="emit('starter', starter)">{{ starter }} <span aria-hidden="true">↗</span></button></div>
    </section>
    <template v-else>
      <article v-for="(message, index) in messages" :key="`${message.analysis_job_id}-${index}`" class="message-card" :class="message.sender">
        <div class="message-avatar" :class="message.sender">{{ message.sender === 'user' ? '你' : '∑' }}</div>
        <div class="message-body"><div class="message-label">{{ message.sender === 'user' ? '你的问题' : 'MathAgent' }}</div><p>{{ message.text }}</p></div>
      </article>
    </template>
  </div>
</template>
