<script setup lang="ts">
/**
 * Admin Agent Trace 页面
 *
 * 功能：
 *  - 按 messageId 查单次 agent 完整 trace
 *  - 按 conversationId 查会话最近 N 条 message 摘要
 *  - 步骤时间轴（van-steps），每步可展开 args / output
 *
 * 鉴权：route meta.requiresAdmin，roleId === 1
 */

import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  fetchAgentTrace,
  fetchAgentTraceSummary,
  type TraceStep,
  type TraceMessage,
  type TraceSummary,
} from '@/api/trace'

const message = useMessage()

const searchMessageId = ref<number | null>(null)
const searchConvId = ref<number | null>(null)
const traceMessage = ref<TraceMessage | null>(null)
const traceSteps = ref<TraceStep[]>([])
const traceSummary = ref<TraceSummary[]>([])
const loading = ref(false)

async function loadTrace() {
  if (!searchMessageId.value) {
    message.warning('请输入 messageId')
    return
  }
  loading.value = true
  try {
    const result = await fetchAgentTrace(searchMessageId.value)
    traceMessage.value = result.message
    traceSteps.value = result.steps
    traceSummary.value = []
  } catch (e) {
    message.error('加载 trace 失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  if (!searchConvId.value) {
    message.warning('请输入 conversationId')
    return
  }
  loading.value = true
  try {
    traceMessage.value = null
    traceSteps.value = []
    traceSummary.value = await fetchAgentTraceSummary(searchConvId.value)
    if (traceSummary.value.length === 0) {
      message.warning('该会话暂无 assistant 消息')
    }
  } catch (e) {
    message.error('加载摘要失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function openFromSummary(s: TraceSummary) {
  searchMessageId.value = s.messageId
  loadTrace()
}

// URL query 自动加载：/admin/trace?messageId=847
const route = useRoute()
if (route.query.messageId) {
  const mid = parseInt(route.query.messageId as string, 10)
  if (!isNaN(mid) && mid > 0) {
    searchMessageId.value = mid
    loadTrace()
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<template>
  <div class="admin-trace-page">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">←</button>
      <h2>Agent Trace</h2>
      <div class="header-right">
        <n-button quaternary circle @click="$router.push('/admin/architecture')" title="架构图">
          <template #icon><span>🏗</span></template>
        </n-button>
      </div>
    </div>

    <div class="content">
      <div class="search-row">
        <n-input v-model:value="searchMessageId" type="number" placeholder="输入 messageId" clearable />
        <n-button type="primary" size="small" :loading="loading" @click="loadTrace">查看</n-button>
      </div>

      <div class="search-row">
        <n-input v-model:value="searchConvId" type="number" placeholder="输入 conversationId 查列表" clearable />
        <n-button type="primary" size="small" :loading="loading" @click="loadSummary">查列表</n-button>
      </div>

      <div v-if="traceMessage" class="trace-detail">
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">Message ID</span>
            <span class="info-value">{{ traceMessage.id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Role</span>
            <span class="info-value">{{ traceMessage.role }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Steps</span>
            <span class="info-value">{{ traceMessage._count.steps }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Created</span>
            <span class="info-value">{{ formatTime(traceMessage.createdAt) }}</span>
          </div>
          <div class="info-row content-row">
            <span class="info-label">Content</span>
            <div class="content-preview">{{ traceMessage.content.slice(0, 300) }}</div>
          </div>
        </div>

        <h3 class="section-title">Step 时间轴（{{ traceSteps.length }}）</h3>
        <div v-if="traceSteps.length === 0" class="empty">该 message 暂无步骤记录</div>
        <n-steps v-else :current="traceSteps.length - 1" direction="vertical">
          <n-step
            v-for="step in traceSteps"
            :key="step.id"
            :title="`#${step.step} · ${step.type}${step.name ? ': ' + step.name : ''}`"
            :description="step.durationMs !== null ? `耗时：${step.durationMs}ms` : undefined"
            :status="step.error ? 'error' : 'finish'"
          >
            <div v-if="step.error" class="error">Error: {{ step.error }}</div>
            <n-collapse v-if="step.args || step.output" class="step-collapse">
              <n-collapse-item v-if="step.args" title="args" :name="`args-${step.id}`">
                <pre class="json">{{ JSON.stringify(step.args, null, 2) }}</pre>
              </n-collapse-item>
              <n-collapse-item v-if="step.output" title="output" :name="`output-${step.id}`">
                <pre class="json">{{ step.output }}</pre>
              </n-collapse-item>
            </n-collapse>
          </n-step>
        </n-steps>
      </div>

      <div v-else-if="traceSummary.length > 0" class="summary-list">
        <h3 class="section-title">会话 #{{ searchConvId }} 最近消息（{{ traceSummary.length }}）</h3>
        <div class="summary-cards">
          <div
            v-for="s in traceSummary"
            :key="s.messageId"
            class="summary-item"
            @click="openFromSummary(s)"
          >
            <div class="summary-title">#{{ s.messageId }} · {{ s.stepCount }} steps</div>
            <div class="summary-preview">{{ s.preview }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-trace-page {
  min-height: 100vh;
  background: var(--bg-primary);
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
  flex: 1;
}
.header-right {
  margin-left: auto;
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
.content {
  padding: 16px;
  max-width: 800px;
}
.search-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.search-row .n-input {
  flex: 1;
}
.section-title {
  margin: 20px 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.info-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}
.info-row {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  gap: 12px;
}
.info-row + .info-row {
  border-top: 1px solid var(--border-color);
}
.info-label {
  font-size: 13px;
  color: var(--text-secondary);
  min-width: 100px;
  flex-shrink: 0;
}
.info-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}
.content-row {
  flex-direction: column;
  align-items: flex-start;
}
.content-preview {
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  white-space: pre-wrap;
  text-align: left;
  margin-top: 4px;
}
.error { color: #d03050; font-size: 12px; margin-top: 2px; word-break: break-all; }
.step-collapse { margin-top: 6px; }
.json {
  background: var(--bg-primary);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.empty {
  text-align: center;
  color: var(--text-secondary);
  padding: 24px 0;
  font-size: 13px;
}
.summary-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.summary-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  transition: background 0.15s;
}
.summary-item:hover {
  background: var(--border-color);
}
.summary-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.summary-preview {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
