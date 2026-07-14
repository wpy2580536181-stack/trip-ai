<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import sysSvg from '@/assets/architecture/system-architecture.svg'
import agentSvg from '@/assets/architecture/agent-sequence.svg'
import ragSvg from '@/assets/architecture/rag-pipeline.svg'
import ctxSvg from '@/assets/architecture/context-data-flow.svg'
import evSvg from '@/assets/architecture/evaluation-system.svg'

const router = useRouter()
const activeTab = ref<number>(0)

const tabs = [
  { name: 0, title: '系统架构', src: sysSvg },
  { name: 1, title: 'Agent 时序', src: agentSvg },
  { name: 2, title: 'RAG 检索链路', src: ragSvg },
  { name: 3, title: '上下文流', src: ctxSvg },
  { name: 4, title: '评估体系', src: evSvg },
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
          <img class="arch-img" :src="t.src" :alt="t.title" />
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
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  background: #fafafa;
}
.arch-img {
  max-width: 100%;
  height: auto;
  border: 1px solid #eee;
  border-radius: 12px;
  background: #fafafa;
}
</style>
