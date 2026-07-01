<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import SystemArchitecture from '@/components/architecture/SystemArchitecture.vue'
import AgentSequence from '@/components/architecture/AgentSequence.vue'
import RagPipeline from '@/components/architecture/RagPipeline.vue'
import ContextDataFlow from '@/components/architecture/ContextDataFlow.vue'
import EvaluationSystem from '@/components/architecture/EvaluationSystem.vue'

const router = useRouter()
const activeTab = ref<number>(0)

const tabs = [
  { name: 0, title: '系统架构' },
  { name: 1, title: 'Agent 时序' },
  { name: 2, title: 'RAG 检索链路' },
  { name: 3, title: '上下文流' },
  { name: 4, title: '评估体系' },
]

function onBack() {
  router.back()
}
</script>

<template>
  <div class="arch-view">
    <div class="page-header">
      <button class="back-btn" @click="onBack">←</button>
      <h2>🏗 系统架构图</h2>
    </div>
    <n-tabs v-model:value="activeTab" animated>
      <n-tab-pane v-for="t in tabs" :key="t.name" :name="t.name" :tab="t.title">
        <div class="diagram-container">
          <SystemArchitecture v-if="t.name === 0" />
          <AgentSequence v-else-if="t.name === 1" />
          <RagPipeline v-else-if="t.name === 2" />
          <ContextDataFlow v-else-if="t.name === 3" />
          <EvaluationSystem v-else-if="t.name === 4" />
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.arch-view {
  min-height: 100vh;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-radius: 12px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  border-radius: 12px 12px 0 0;
}
.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}
.back-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  color: var(--text-primary);
  line-height: 1;
}
.diagram-container {
  width: 100%;
  height: calc(100vh - 96px);
  min-height: 520px;
}
</style>
