<script setup lang="ts">
/**
 * Admin Architecture Viewer
 *
 * 4 张架构图（系统 / 时序 / 上下文 / 评估），用 Vant tabs 切换
 * 鉴权：route meta.requiresAdmin，roleId === 1
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import SystemArchitecture from '@/components/architecture/SystemArchitecture.vue'
import AgentSequence from '@/components/architecture/AgentSequence.vue'
import ContextDataFlow from '@/components/architecture/ContextDataFlow.vue'
import EvaluationSystem from '@/components/architecture/EvaluationSystem.vue'

interface Tab {
  name: number
  title: string
}

const router = useRouter()
const activeTab = ref<number>(0)

const tabs: Tab[] = [
  { name: 0, title: '系统架构' },
  { name: 1, title: 'Agent 时序' },
  { name: 2, title: '上下文流' },
  { name: 3, title: '评估体系' },
]

function onTabClick(tab: { name: number | string }) {
  activeTab.value = Number(tab.name)
  showToast(`切换到: ${tabs[activeTab.value]?.title}`)
}

function onBack() {
  router.back()
}
</script>

<template>
  <div class="arch-view">
    <van-nav-bar title="🏗 系统架构图" left-arrow @click-left="onBack" />
    <van-tabs v-model:active="activeTab" sticky animated swipeable @click-tab="onTabClick">
      <van-tab v-for="t in tabs" :key="t.name" :title="t.title" :name="t.name">
        <div class="diagram-container">
          <SystemArchitecture v-if="t.name === 0" />
          <AgentSequence v-else-if="t.name === 1" />
          <ContextDataFlow v-else-if="t.name === 2" />
          <EvaluationSystem v-else-if="t.name === 3" />
        </div>
      </van-tab>
    </van-tabs>
  </div>
</template>

<style scoped>
.arch-view {
  min-height: 100vh;
  background: #fafafa;
  display: flex;
  flex-direction: column;
}
.diagram-container {
  width: 100%;
  height: calc(100vh - 96px);
  min-height: 520px;
}
</style>
